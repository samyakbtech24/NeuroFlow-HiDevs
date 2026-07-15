import asyncio
import json
import logging
import uuid

from backend.db.pool import get_pool
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.context_assembler import assemble_context
from pipelines.generation.prompt_builder import PromptBuilder

# Import the metrics asynchronously or safely to bypass circular calls
from evaluation.metrics.faithfulness import evaluate_faithfulness
from evaluation.metrics.answer_relevance import evaluate_answer_relevance
from evaluation.metrics.context_precision import evaluate_context_precision
from evaluation.metrics.context_recall import evaluate_context_recall

logger = logging.getLogger("eval-judge")

# Attempt setup for OpenTelemetry
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("neuroflow-judge")
except ImportError:
    tracer = None
    logger.warning("OpenTelemetry trace library not available. Evaluation tracking spans are disabled.")

class EvaluationJudge:
    """
    Automated RAG evaluation coordinator. Runs Faithfulness, Answer Relevance,
    Context Precision, and Context Recall in parallel, logs metrics to Postgres,
    and curates high-performing pairs for fine-tuning.
    """
    
    async def evaluate_run(self, run_id: uuid.UUID) -> dict:
        """
        Executes the evaluation for a given pipeline run ID.
        """
        pool = get_pool()
        
        # 1. Fetch the run log details from database
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT query, retrieved_chunk_ids, generation, pipeline_id
                    FROM pipeline_runs
                    WHERE id = $1
                    """,
                    run_id
                )
            if not row:
                raise ValueError(f"Pipeline run {run_id} not found.")
                
            query = row["query"]
            chunk_ids = row["retrieved_chunk_ids"] or []
            generation = row["generation"]
            pipeline_id = row["pipeline_id"]
        except Exception as e:
            logger.error(f"Failed to fetch pipeline_run for evaluation {run_id}: {e}")
            return {}

        # 2. Reconstruct retrieved chunks text and metadata
        chunks_text = []
        try:
            async with pool.acquire() as conn:
                # Fetch retrieved chunks details matching saved list IDs
                if chunk_ids:
                    chunk_rows = await conn.fetch(
                        "SELECT id, content, metadata FROM chunks WHERE id = any($1)",
                        chunk_ids
                    )
                    # Maintain initial retrieval ordering
                    row_map = {r["id"]: r for r in chunk_rows}
                    chunks_text = [row_map[cid]["content"] for cid in chunk_ids if cid in row_map]
        except Exception as e:
            logger.error(f"Failed to fetch chunks details for evaluation {run_id}: {e}")

        context_str = "\n".join(chunks_text)

        # 3. Execute all 4 metrics in parallel using asyncio.gather
        try:
            faithfulness_task = evaluate_faithfulness(query, generation, context_str)
            relevance_task = evaluate_answer_relevance(query, generation)
            precision_task = evaluate_context_precision(query, chunks_text, generation)
            recall_task = evaluate_context_recall(query, chunks_text, generation)
            
            faithfulness, relevance, precision, recall = await asyncio.gather(
                faithfulness_task, relevance_task, precision_task, recall_task
            )
        except Exception as e:
            logger.error(f"Failed during metrics calculations for run {run_id}: {e}")
            # Safe default fallback scores
            faithfulness, relevance, precision, recall = 0.5, 0.5, 0.5, 0.5

        # 4. Calculate weighted overall score
        overall_score = (
            0.35 * faithfulness + 
            0.30 * relevance + 
            0.20 * precision + 
            0.15 * recall
        )
        overall_score = round(overall_score, 4)

        # 5. Write the evaluation results to evaluations database table
        eval_id = uuid.uuid4()
        judge_model = "gpt-4o-mini"  # Routed evaluation model name
        
        try:
            async with pool.acquire() as conn:
                # Check if a row already exists (inserted by user rating PATCH route)
                existing_row = await conn.fetchrow(
                    "SELECT id, user_rating FROM evaluations WHERE run_id = $1",
                    run_id
                )
                
                if existing_row:
                    user_rating = existing_row["user_rating"]
                    calibration_needed = False
                    if user_rating is not None:
                        if abs(overall_score - (user_rating / 5.0)) > 0.3:
                            calibration_needed = True
                            
                    await conn.execute(
                        """
                        UPDATE evaluations
                        SET faithfulness = $1,
                            answer_relevance = $2,
                            context_precision = $3,
                            context_recall = $4,
                            overall_score = $5,
                            judge_model = $6,
                            metadata = jsonb_set(metadata, '{calibration_needed}', $7::jsonb)
                        WHERE run_id = $8
                        """,
                        faithfulness,
                        relevance,
                        precision,
                        recall,
                        overall_score,
                        judge_model,
                        json.dumps(calibration_needed),
                        run_id
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO evaluations (id, run_id, faithfulness, answer_relevance, context_precision, context_recall, overall_score, judge_model, metadata, evaluated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW())
                        """,
                        eval_id,
                        run_id,
                        faithfulness,
                        relevance,
                        precision,
                        recall,
                        overall_score,
                        judge_model,
                        json.dumps({"calibration_needed": False})
                    )
            logger.info(f"Saved automated evaluation for run {run_id}: Overall Score = {overall_score}")
            
            # Publish evaluation notification to Redis for SSE Feed
            try:
                import redis.asyncio as aioredis
                from backend.config import settings
                redis_client = aioredis.from_url(settings.redis_url)
                eval_data = {
                    "run_id": str(run_id),
                    "pipeline_id": str(pipeline_id),
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "overall_score": overall_score,
                    "metrics": {
                        "faithfulness": faithfulness,
                        "relevance": relevance,
                        "precision": precision,
                        "recall": recall
                    }
                }
                await redis_client.publish("evaluations:new", json.dumps(eval_data))
                await redis_client.aclose()
            except Exception as e:
                logger.error(f"Failed to publish evaluation to Redis: {e}")

        except Exception as e:
            logger.error(f"Failed to write evaluation record to database: {e}")

        # 6. Training pair extraction if overall_score > 0.8
        if overall_score > 0.8:
            try:
                # Reconstruct full prompt messages sent to LLM
                prompt_builder = PromptBuilder()
                # Query classification type logic fallback
                query_type = "factual"
                messages = prompt_builder.build_prompt(query, context_str, query_type)
                
                system_prompt = messages[0].content if len(messages) > 0 else ""
                user_message = messages[1].content if len(messages) > 1 else query
                
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO training_pairs (id, run_id, system_prompt, user_message, assistant_message)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT DO NOTHING
                        """,
                        uuid.uuid4(),
                        run_id,
                        system_prompt,
                        user_message,
                        generation
                    )
                logger.info(f"Curated RAG run {run_id} into training_pairs table for fine-tuning.")
            except Exception as e:
                logger.error(f"Failed to save training pair for run {run_id}: {e}")

        # 7. Emit OpenTelemetry span evaluation.judge with metrics attributes
        if tracer:
            with tracer.start_as_current_span("evaluation.judge") as span:
                span.set_attribute("run_id", str(run_id))
                span.set_attribute("faithfulness", faithfulness)
                span.set_attribute("answer_relevance", relevance)
                span.set_attribute("context_precision", precision)
                span.set_attribute("context_recall", recall)
                span.set_attribute("overall_score", overall_score)

        return {
            "evaluation_id": str(eval_id),
            "run_id": str(run_id),
            "faithfulness": faithfulness,
            "answer_relevance": relevance,
            "context_precision": precision,
            "context_recall": recall,
            "overall_score": overall_score
        }
