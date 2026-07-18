import asyncio
import json
import logging
import time
import contextlib
from typing import AsyncGenerator, List, Dict, Any
import uuid
import tiktoken
import redis.asyncio as aioredis

from backend.config import settings
from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria
from pipelines.generation.prompt_builder import PromptBuilder
from pipelines.generation.citations import parse_citations

from backend.monitoring.metrics import generation_latency, llm_cost, lm_calls_total

logger = logging.getLogger("rag-generator")

try:
    from opentelemetry import trace
    tracer = trace.get_tracer("neuroflow-generator")
except ImportError:
    tracer = None

class RAGGenerator:
    """
    Manages the RAG generation phase: prompt building, streaming completions from the routed LLM,
    citation post-processing, database telemetry logging, and background evaluation enqueuing.
    """
    
    def __init__(self):  # type: ignore
        self.prompt_builder = PromptBuilder()
        self.client = NeuroFlowClient()

    async def _enqueue_eval_job(self, run_id: uuid.UUID, pipeline_id: uuid.UUID):  # type: ignore
        """
        Pushes an evaluation job asynchronously to the Redis queue 'queue:eval'.
        """
        try:
            redis_client = aioredis.from_url(settings.redis_url)
            payload = {
                "run_id": str(run_id),
                "pipeline_id": str(pipeline_id)
            }
            await redis_client.lpush("queue:eval", json.dumps(payload))
            await redis_client.aclose()
            logger.info(f"Asynchronously enqueued evaluation job for run {run_id} to Redis.")
        except Exception as e:
            logger.error(f"Failed to enqueue evaluation job to Redis: {e}")

    async def generate_stream(
        self,
        query: str,
        context: str,
        query_type: str,
        run_id: uuid.UUID,
        pipeline_id: uuid.UUID,
        context_chunks: List[Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        
        start_time = time.time()
        parent_ctx = tracer.start_as_current_span("generation.pipeline") if tracer else contextlib.nullcontext()
        
        with parent_ctx as parent_span:
            if parent_span and hasattr(parent_span, "set_attribute"):
                parent_span.set_attribute("run_id", str(run_id))
                parent_span.set_attribute("pipeline_id", str(pipeline_id))

            # 1. Build prompt
            prompt_ctx = tracer.start_as_current_span("generation.prompt_build") if tracer else contextlib.nullcontext()
            with prompt_ctx:
                messages = self.prompt_builder.build_prompt(query, context, query_type)
                prompt_str = "".join([m.content for m in messages if isinstance(m.content, str)])
                logger.info(f"Assembled Prompt for run {run_id}:\n{prompt_str}")

            # 2. Route the model using the router criteria
            criteria = RoutingCriteria(task_type="generation")
            try:
                model_config = await self.client.router.route(criteria)
                provider_name = model_config["provider"]
                model_id = model_config["model_id"]
            except Exception as e:
                logger.error(f"Routing failed: {e}. Falling back to default gpt-4o-mini.")
                provider_name = "openai"
                model_id = "gpt-4o-mini"

            provider = self.client._get_provider(provider_name, model_id)
            
            # Prometheus metrics
            lm_calls_total.labels(provider=provider_name, model=model_id, task_type="generation").inc()
            
            # 3. Stream tokens from the model provider
            response_text = ""
            llm_ctx = tracer.start_as_current_span("generation.llm_call") if tracer else contextlib.nullcontext()
            with llm_ctx as llm_span:
                if llm_span and hasattr(llm_span, "set_attribute"):
                    llm_span.set_attribute("model", model_id)
                    llm_span.set_attribute("provider", provider_name)
                    
                try:
                    async for token in provider.stream(messages):
                        response_text += token
                        yield {"type": "token", "delta": token}
                except Exception as e:
                    logger.error(f"Streaming token generation failed: {e}")
                    yield {"type": "error", "message": str(e)}
                    return

            # 4. Stream completed successfully. Calculate metrics.
            latency_seconds = time.time() - start_time
            latency_ms = int(latency_seconds * 1000)
            
            generation_latency.labels(model=model_id).observe(latency_seconds)
            
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                input_tokens = len(encoding.encode(prompt_str))
                output_tokens = len(encoding.encode(response_text))
            except Exception:
                input_tokens = max(1, sum(len(m.content.split()) for m in messages if isinstance(m.content, str)))
                output_tokens = max(1, len(response_text.split()))

            # Approximate cost tracking ($0.15/1M in, $0.60/1M out for mini, etc.)
            cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1000000.0
            llm_cost.labels(model=model_id).observe(cost)

            if parent_span and hasattr(parent_span, "set_attribute"):
                parent_span.set_attribute("input_tokens", input_tokens)
                parent_span.set_attribute("output_tokens", output_tokens)

            # 5. Parse and resolve citations
            cite_ctx = tracer.start_as_current_span("generation.citation_parse") if tracer else contextlib.nullcontext()
            with cite_ctx:
                citations = parse_citations(response_text, context_chunks)
            
            # 6. Update database row
            db_ctx = tracer.start_as_current_span("generation.log_run") if tracer else contextlib.nullcontext()
            with db_ctx:
                pool = get_pool()
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE pipeline_runs
                            SET generation = $1,
                                latency_ms = $2,
                                input_tokens = $3,
                                output_tokens = $4,
                                model_used = $5,
                                status = 'complete'
                            WHERE id = $6
                            """,
                            response_text,
                            latency_ms,
                            input_tokens,
                            output_tokens,
                            model_id,
                            run_id
                        )
                    logger.info(f"Updated pipeline_runs for {run_id}: complete ({output_tokens} tokens generated).")
                except Exception as e:
                    logger.error(f"Failed to update pipeline_runs database: {e}")

            # 7. Asynchronously trigger evaluation job in Redis
            asyncio.create_task(self._enqueue_eval_job(run_id, pipeline_id))

            # 8. Yield the final done event containing citations
            yield {
                "type": "done",
                "run_id": str(run_id),
                "citations": citations
            }
