import asyncio
import uuid
import time
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from backend.db.pool import get_pool
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.context_assembler import assemble_context
from pipelines.generation.generator import RAGGenerator

router = APIRouter(prefix="/pipelines/compare", tags=["compare"])

class CompareRequest(BaseModel):
    query: str = Field(..., description="The user search query")
    pipeline_a_id: uuid.UUID = Field(..., description="UUID of Pipeline A")
    pipeline_b_id: uuid.UUID = Field(..., description="UUID of Pipeline B")

async def execute_pipeline_run(query: str, pipeline_id: uuid.UUID) -> Dict[str, Any]:
    """
    Executes a blocking RAG run for a specific pipeline and returns execution metrics.
    """
    run_id = uuid.uuid4()
    pool = get_pool()
    start_time = time.time()
    
    # 1. Fetch current pipeline version
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT version FROM pipelines WHERE id = $1 AND status != 'archived'", pipeline_id)
        if not row:
            raise ValueError(f"Pipeline {pipeline_id} not found or archived.")
        pipeline_version = row["version"]
        
        # Insert run record
        await conn.execute(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, pipeline_version, query, status, created_at)
            VALUES ($1, $2, $3, $4, 'running', NOW())
            """,
            run_id, pipeline_id, pipeline_version, query
        )

    try:
        # 2. Retrieval
        retrieval_start = time.time()
        retriever = Retriever()
        chunks = await retriever.retrieve(query)
        chunk_ids = [uuid.UUID(c.chunk_id) for c in chunks]
        retrieval_time_ms = int((time.time() - retrieval_start) * 1000)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE pipeline_runs SET retrieved_chunk_ids = $1 WHERE id = $2",
                chunk_ids, run_id
            )

        # 3. Generation
        context_dict = assemble_context(chunks)
        query_type = await retriever.processor.classify_query(query)
        
        generator = RAGGenerator()
        generation_text = ""
        
        async for event in generator.generate_stream(
            query=query,
            context=context_dict["context"],
            query_type=query_type,
            run_id=run_id,
            pipeline_id=pipeline_id,
            context_chunks=chunks
        ):
            if event["type"] == "token":
                generation_text += event["delta"]

        total_time_ms = int((time.time() - start_time) * 1000)
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipeline_runs 
                SET generation = $1, latency_ms = $2, input_tokens = $3, output_tokens = $4, status = 'completed'
                WHERE id = $5
                """,
                generation_text, total_time_ms, 150, 50, run_id # Using 150/50 as mock token counts
            )
        
        return {
            "run_id": str(run_id),
            "generation": generation_text,
            "retrieval_latency_ms": retrieval_time_ms,
            "total_latency_ms": total_time_ms,
            "chunks_used": len(chunks),
            # Mock eval_score for immediate response (real eval happens asynchronously in background)
            "eval_score": None 
        }
    except Exception as e:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE pipeline_runs SET status = 'failed' WHERE id = $1", run_id)
        return {"error": str(e), "run_id": str(run_id)}

@router.post("")
async def compare_pipelines(request: CompareRequest, background_tasks: BackgroundTasks):
    """
    Executes two RAG pipelines in parallel and returns side-by-side results.
    Enqueues evaluation jobs for both runs automatically.
    """
    try:
        # Execute both pipelines concurrently using scatter-gather pattern
        results = await asyncio.gather(
            execute_pipeline_run(request.query, request.pipeline_a_id),
            execute_pipeline_run(request.query, request.pipeline_b_id),
            return_exceptions=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    res_a, res_b = results
    
    # Check if either raised an exception
    if isinstance(res_a, Exception):
        res_a = {"error": str(res_a)}
    if isinstance(res_b, Exception):
        res_b = {"error": str(res_b)}
        
    # Enqueue background evaluation jobs for both runs (if successful)
    # The evaluation judge runs independently of the request/response lifecycle.
    def trigger_eval(run_dict):
        if "run_id" in run_dict and "error" not in run_dict:
            from evaluation.judge import EvaluationJudge
            # Using fire-and-forget for background evaluation
            asyncio.create_task(EvaluationJudge().evaluate_run(uuid.UUID(run_dict["run_id"])))
            
    background_tasks.add_task(trigger_eval, res_a)
    background_tasks.add_task(trigger_eval, res_b)
        
    return {
        "query": request.query,
        "pipeline_a": res_a,
        "pipeline_b": res_b
    }
