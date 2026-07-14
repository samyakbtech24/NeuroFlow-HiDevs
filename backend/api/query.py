import asyncio
import json
import logging
import uuid
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.db.pool import get_pool
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.context_assembler import assemble_context
from pipelines.generation.generator import RAGGenerator

logger = logging.getLogger("query-api")

router = APIRouter()

class QueryRequest(BaseModel):
    """
    Schema for user search query request.
    """
    query: str = Field(..., description="The user search query or question")
    pipeline_id: uuid.UUID = Field(..., description="UUID of the RAG pipeline configurations to use")
    stream: bool = Field(default=True, description="Whether to stream tokens via SSE or return full JSON response")

class QueryResponse(BaseModel):
    """
    Schema for blocking (non-streamed) RAG response.
    """
    run_id: uuid.UUID
    generation: str
    citations: List[dict]

@router.post("/query")
async def create_query(request: QueryRequest):
    """
    Initializes a query execution run:
    1. Creates a new run_id.
    2. Logs the run record into the pipeline_runs table as 'running'.
    3. Returns run_id immediately if stream=True, else executes the RAG pipeline blocking.
    """
    run_id = uuid.uuid4()
    pool = get_pool()
    
    # Verify pipeline exists first
    try:
        async with pool.acquire() as conn:
            pipeline_exists = await conn.fetchval("SELECT 1 FROM pipelines WHERE id = $1", request.pipeline_id)
            if not pipeline_exists:
                # If pipeline doesn't exist, seed a dummy pipeline config so the execution doesn't block
                # in case the UI testing hasn't initialized the pipeline table yet.
                await conn.execute(
                    """
                    INSERT INTO pipelines (id, name, config, created_at)
                    VALUES ($1, $2, $3::jsonb, NOW())
                    ON CONFLICT DO NOTHING
                    """,
                    request.pipeline_id,
                    f"Pipeline-{request.pipeline_id}",
                    json.dumps({"model": "gpt-4o-mini", "temperature": 0.0})
                )
    except Exception as e:
        logger.error(f"Pipeline verification check failed: {e}")

    # 1. Log running task inside pipeline_runs database
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pipeline_runs (id, pipeline_id, query, retrieved_chunk_ids, status, created_at)
                VALUES ($1, $2, $3, NULL, 'running', NOW())
                """,
                run_id,
                request.pipeline_id,
                request.query
            )
        logger.info(f"Initialized query run {run_id} (stream={request.stream})")
    except Exception as e:
        logger.error(f"Failed to insert pipeline_run record: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize query run state in database."
        )

    # 2. Return run_id immediately if streaming
    if request.stream:
        return {"run_id": str(run_id)}

    # 3. Non-streaming blocking path
    try:
        retriever = Retriever()
        chunks = await retriever.retrieve(request.query)
        chunk_ids = [uuid.UUID(c.chunk_id) for c in chunks]
        
        # Update retrieved chunk IDs in DB
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE pipeline_runs SET retrieved_chunk_ids = $1 WHERE id = $2",
                chunk_ids,
                run_id
            )
            
        context_dict = assemble_context(chunks)
        query_type = await retriever.processor.classify_query(request.query)
        
        generator = RAGGenerator()
        generation_text = ""
        citations = []
        
        # Accumulate streaming events synchronously
        async for event in generator.generate_stream(
            query=request.query,
            context=context_dict["context"],
            query_type=query_type,
            run_id=run_id,
            pipeline_id=request.pipeline_id,
            context_chunks=chunks
        ):
            if event["type"] == "token":
                generation_text += event["delta"]
            elif event["type"] == "done":
                citations = event["citations"]
                
        return {
            "run_id": str(run_id),
            "generation": generation_text,
            "citations": citations
        }
    except Exception as e:
        logger.error(f"Blocking RAG generation execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution error: {str(e)}"
        )

@router.get("/query/{run_id}/stream")
async def query_stream(run_id: uuid.UUID, request: Request):
    """
    SSE stream endpoint pushing progress events (retrieval_start, retrieval_complete, token, done)
    to client browser EventSource connections.
    """
    async def event_generator():
        pool = get_pool()
        
        # 1. Fetch query details from DB
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT query, pipeline_id FROM pipeline_runs WHERE id = $1", 
                    run_id
                )
            if not row:
                yield {"data": json.dumps({"type": "error", "message": "Run execution not found."})}
                return
            query = row["query"]
            pipeline_id = row["pipeline_id"]
        except Exception as e:
            yield {"data": json.dumps({"type": "error", "message": f"Database lookup failed: {e}"})}
            return

        # 2. Emit retrieval start
        yield {"data": json.dumps({"type": "retrieval_start"})}
        
        # 3. Run retrieval pipeline
        try:
            retriever = Retriever()
            chunks = await retriever.retrieve(query)
            chunk_ids = [uuid.UUID(c.chunk_id) for c in chunks]
        except Exception as e:
            yield {"data": json.dumps({"type": "error", "message": f"Retrieval failed: {e}"})}
            return
            
        # 4. Update retrieved chunk IDs in DB
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pipeline_runs SET retrieved_chunk_ids = $1 WHERE id = $2",
                    chunk_ids,
                    run_id
                )
        except Exception as e:
            logger.error(f"Failed to update chunk IDs for run {run_id}: {e}")

        # 5. Emit retrieval complete
        sources = [c.metadata.get("filename", "Unknown Document") for c in chunks]
        yield {
            "data": json.dumps({
                "type": "retrieval_complete",
                "chunk_count": len(chunks),
                "sources": list(set(sources))
            })
        }

        # 6. Format context
        context_dict = assemble_context(chunks)
        
        # 7. Classify query type
        query_type = await retriever.processor.classify_query(query)
        
        # 8. Start generation streaming
        generator = RAGGenerator()
        async for event in generator.generate_stream(
            query=query,
            context=context_dict["context"],
            query_type=query_type,
            run_id=run_id,
            pipeline_id=pipeline_id,
            context_chunks=chunks
        ):
            yield {"data": json.dumps(event)}

    # EventSourceResponse automatically sends comment keepalives (ping=15 seconds) to prevent proxy timeouts.
    return EventSourceResponse(event_generator(), ping=15)

class RatingRequest(BaseModel):
    """
    Schema for updating human feedback rating.
    """
    rating: int = Field(..., ge=1, le=5, description="Human score between 1 and 5")

@router.patch("/runs/{run_id}/rating")
async def update_run_rating(run_id: uuid.UUID, body: RatingRequest):
    """
    Saves human rating feedback, compares it to automated overall score,
    and flags calibration needs in JSONB metadata.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            # 1. Verify pipeline run exists
            run_exists = await conn.fetchval("SELECT 1 FROM pipeline_runs WHERE id = $1", run_id)
            if not run_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Pipeline run execution not found."
                )

            # 2. Check if automated evaluation row already exists
            row = await conn.fetchrow(
                "SELECT overall_score, metadata FROM evaluations WHERE run_id = $1", 
                run_id
            )
            
            user_score = body.rating / 5.0
            calibration_needed = False
            
            if row:
                overall_score = row["overall_score"]
                if overall_score is not None:
                    if abs(overall_score - user_score) > 0.3:
                        calibration_needed = True
                
                # Retrieve existing metadata dict
                try:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                except Exception:
                    metadata = {}
                metadata["calibration_needed"] = calibration_needed
                
                await conn.execute(
                    "UPDATE evaluations SET user_rating = $1, metadata = $2::jsonb WHERE run_id = $3",
                    body.rating,
                    json.dumps(metadata),
                    run_id
                )
            else:
                # No automated evaluations completed yet: save user rating and insert placeholder
                await conn.execute(
                    """
                    INSERT INTO evaluations (id, run_id, user_rating, metadata, evaluated_at)
                    VALUES ($1, $2, $3, $4::jsonb, NOW())
                    """,
                    uuid.uuid4(),
                    run_id,
                    body.rating,
                    json.dumps({"calibration_needed": False})
                )
                
            return {
                "status": "success",
                "message": "User feedback rating recorded successfully.",
                "calibration_needed": calibration_needed
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record rating for run {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record human feedback: {str(e)}"
        )

