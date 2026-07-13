import asyncio
import json
import logging
import time
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

logger = logging.getLogger("rag-generator")

class RAGGenerator:
    """
    Manages the RAG generation phase: prompt building, streaming completions from the routed LLM,
    citation post-processing, database telemetry logging, and background evaluation enqueuing.
    """
    
    def __init__(self):
        self.prompt_builder = PromptBuilder()
        self.client = NeuroFlowClient()

    async def _enqueue_eval_job(self, run_id: uuid.UUID, pipeline_id: uuid.UUID):
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
        """
        Streams generated tokens, updates run stats in PostgreSQL, enqueues evaluation,
        and yields final structured citations.
        """
        start_time = time.time()
        
        # 1. Build prompt
        messages = self.prompt_builder.build_prompt(query, context, query_type)
        prompt_str = "".join([m.content for m in messages if isinstance(m.content, str)])
        
        # Log the complete prompt to logger (and we will write it to console / debug)
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
        
        # 3. Stream tokens from the model provider
        response_text = ""
        try:
            async for token in provider.stream(messages):
                response_text += token
                yield {"type": "token", "delta": token}
        except Exception as e:
            logger.error(f"Streaming token generation failed: {e}")
            yield {"type": "error", "message": str(e)}
            return

        # 4. Stream completed successfully. Calculate metrics.
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Calculate tokens using tiktoken (cl100k_base is used by OpenAI models)
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            input_tokens = len(encoding.encode(prompt_str))
            output_tokens = len(encoding.encode(response_text))
        except Exception:
            # Word-count fallback approximation
            input_tokens = max(1, sum(len(m.content.split()) for m in messages if isinstance(m.content, str)))
            output_tokens = max(1, len(response_text.split()))

        # 5. Parse and resolve citations
        citations = parse_citations(response_text, context_chunks)
        
        # 6. Update database row in pipeline_runs to 'complete' with metrics
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

        # 7. Asynchronously trigger evaluation job in Redis without awaiting it
        asyncio.create_task(self._enqueue_eval_job(run_id, pipeline_id))

        # 8. Yield the final done event containing citations
        yield {
            "type": "done",
            "run_id": str(run_id),
            "citations": citations
        }
