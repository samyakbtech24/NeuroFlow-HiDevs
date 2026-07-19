import asyncio
import base64
import contextlib
import json
import logging
import time
import uuid

import redis.asyncio as aioredis

from backend.config import settings
from backend.db.pool import close_pool, get_pool, init_pool
from backend.monitoring.metrics import ingestion_docs_total
from backend.providers.client import NeuroFlowClient
from backend.security.prompt_injection import scan_patterns
from backend.security.secret_detector import scan_and_redact
from pipelines.ingestion.chunker import chunk_document, count_tokens
from pipelines.ingestion.extractors.csv_extractor import extract_csv
from pipelines.ingestion.extractors.docx_extractor import extract_docx
from pipelines.ingestion.extractors.extracted_page import ExtractedPage
from pipelines.ingestion.extractors.image_extractor import extract_image
from pipelines.ingestion.extractors.pdf_extractor import extract_pdf
from pipelines.ingestion.extractors.url_extractor import extract_url

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

# Setup OpenTelemetry Tracing
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("neuroflow-worker")
except ImportError:
    tracer = None
    logger.warning("OpenTelemetry trace library not available. Worker process tracing is disabled.")

async def process_ingestion_task(task_payload: dict) -> None:  # type: ignore
    doc_id = task_payload["document_id"]
    source_type = task_payload["source_type"]
    task_payload["file_path"]

    start_time = time.time()
    logger.info(f"Starting ingestion process for document {doc_id} ({source_type})")

    pool = get_pool()
    
    # 1. Update status to 'processing'
    async with pool.acquire() as conn:
        await conn.execute("UPDATE documents SET status = 'processing' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
        doc_row = await conn.fetchrow("SELECT filename, metadata FROM documents WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501

    if not doc_row:
        logger.error(f"Document {doc_id} not found in database.")
        return

    metadata = json.loads(doc_row["metadata"]) if doc_row["metadata"] else {}
    filename = doc_row["filename"]

    # Wrap the entire process in a parent span
    parent_context = tracer.start_as_current_span("ingestion.process") if tracer else contextlib.nullcontext()  # noqa: E501
    with parent_context as parent_span:
        if parent_span and hasattr(parent_span, "set_attribute"):
            parent_span.set_attribute("document_id", doc_id)
            parent_span.set_attribute("source_type", source_type)

        # 2. Extract pages
        pages = []
        extract_context = tracer.start_as_current_span(f"ingestion.extract.{source_type}") if tracer else contextlib.nullcontext()  # noqa: E501
        with extract_context:
            try:
                if source_type == "url":
                    url = metadata.get("url")
                    pages = await extract_url(url)  # type: ignore
                else:
                    file_base64 = metadata.get("file_content_base64", "")
                    if not file_base64:
                        raise ValueError("File content missing from database metadata.")
                    file_bytes = base64.b64decode(file_base64)
                    
                    if source_type == "pdf":
                        pages = extract_pdf(file_bytes)
                    elif source_type == "docx":
                        pages = extract_docx(file_bytes)
                    elif source_type == "csv":
                        pages = extract_csv(file_bytes)
                    elif source_type == "image":
                        pages = await extract_image(file_bytes, filename=filename)
                    else:
                        text_content = file_bytes.decode("utf-8", errors="ignore")
                        pages = [ExtractedPage(page_number=1, content=text_content, content_type="text", metadata={})]  # noqa: E501
            except Exception as e:
                logger.error(f"Extraction failed for document {doc_id}: {e}")
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
                return

        page_count = len(pages)
        if page_count == 0:
            logger.error(f"No pages extracted for document {doc_id}.")
            async with pool.acquire() as conn:
                await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
            return
        if parent_span and hasattr(parent_span, "set_attribute"):
            parent_span.set_attribute("page_count", page_count)

        # 3. Chunk pages
        chunk_context = tracer.start_as_current_span("ingestion.chunk") if tracer else contextlib.nullcontext()  # noqa: E501
        with chunk_context:
            try:
                chunks = await chunk_document(pages, {"source_type": source_type, "filename": filename})  # noqa: E501
            except Exception as e:
                logger.error(f"Chunking failed for document {doc_id}: {e}")
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
                return

        chunk_count = len(chunks)
        if chunk_count == 0:
            logger.error(f"No chunks generated for document {doc_id}.")
            async with pool.acquire() as conn:
                await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
            return
        if parent_span and hasattr(parent_span, "set_attribute"):
            parent_span.set_attribute("chunk_count", chunk_count)

        # 4. Generate Embeddings & Save Chunks
        client = NeuroFlowClient()
        embedding_calls = 0
        total_tokens = 0
        
        try:
            async with pool.acquire() as conn:
                # Wrap all database inserts in a single transaction block
                async with conn.transaction():
                    for idx, chunk in enumerate(chunks):
                        content = chunk["content"]
                        
                        # Security Scanning
                        content, redacted = scan_and_redact(content, str(doc_id))
                        is_injection, pattern = scan_patterns(content)
                        
                        chunk_meta = chunk.get("metadata", {})
                        if is_injection:
                            chunk_meta["prompt_injection_detected"] = True
                            chunk_meta["pattern"] = pattern
                        if redacted:
                            chunk_meta["secret_redacted"] = True
                            
                        chunk["content"] = content
                        chunk["metadata"] = chunk_meta
                        
                        token_count = count_tokens(content)
                        total_tokens += token_count
                        
                        # Generate embedding vector
                        embed_context = tracer.start_as_current_span("ingestion.embed") if tracer else contextlib.nullcontext()  # noqa: E501
                        with embed_context as embed_span:
                            embedding_calls += 1
                            vectors = await client.embed([content])
                            vector = vectors[0] if vectors else [0.0] * 1536
                            if embed_span and hasattr(embed_span, "set_attribute"):
                                embed_span.set_attribute("token_count", token_count)
                        
                        # Merge metadata
                        chunk_meta = chunk.get("metadata", {})
                        parent_id = chunk.get("parent_id")
                        if parent_id:
                            chunk_meta["parent_id"] = parent_id

                        db_context = tracer.start_as_current_span("ingestion.write_db") if tracer else contextlib.nullcontext()  # noqa: E501
                        with db_context:
                            await conn.execute(
                                """
                                INSERT INTO chunks (id, document_id, content, embedding, chunk_index, token_count, metadata, created_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                                """,  # noqa: E501
                                uuid.UUID(chunk["id"]),
                                uuid.UUID(doc_id),
                                content,
                                str(vector),
                                idx,
                                token_count,
                                json.dumps(chunk_meta)
                            )

            # 5. Update document to complete
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE documents SET status = 'complete', chunk_count = $1 WHERE id = $2",
                    chunk_count,
                    uuid.UUID(doc_id)
                )
                
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Successfully processed document {doc_id} ({chunk_count} chunks, {total_tokens} tokens)")  # noqa: E501

            if parent_span and hasattr(parent_span, "set_attribute"):
                parent_span.set_attribute("embedding_calls", embedding_calls)
                parent_span.set_attribute("total_tokens", total_tokens)
                parent_span.set_attribute("latency_ms", duration_ms)
                    
            log_json = {
                "event": "ingestion_complete",
                "document_id": doc_id,
                "duration_ms": duration_ms,
                "chunks": chunk_count,
                "tokens": total_tokens
            }
            logger.info("Structured Ingestion Metrics: " + json.dumps(log_json))
            
            # Record Prometheus metric
            ingestion_docs_total.labels(source_type=source_type).inc()
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings or save chunks: {e}")
            async with pool.acquire() as conn:
                await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501

async def main() -> None:
    logger.info("Worker starting up...")
    
    # Initialize connection pool
    await init_pool(settings.database_url)
    
    logger.info("Worker is active and polling for jobs from Redis...")
    
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        while True:
            # Update queue depth metric
            await redis_client.llen("queue:ingest")
            # queue_depth.set(q_len)  # noqa: F821  # type: ignore
            
            # Block and wait for jobs on 'queue:ingest'
            job = await redis_client.brpop("queue:ingest", timeout=1)
            if job:
                # job is a tuple: (b"queue:ingest", b"{payload}")
                _, payload_bytes = job
                try:
                    payload = json.loads(payload_bytes.decode("utf-8"))
                    # Process the task asynchronously
                    await process_ingestion_task(payload)
                except Exception as ex:
                    logger.error(f"Error parsing or processing job: {ex}")
            else:
                # Keep loop alive and cooperative
                await asyncio.sleep(0.1)
                
    except asyncio.CancelledError:
        logger.info("Worker shutdown triggered.")
    finally:
        await close_pool()
        logger.info("Worker connection pool shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
