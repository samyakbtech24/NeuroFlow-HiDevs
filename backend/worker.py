import asyncio
import base64
import json
import logging
import time
import uuid
import redis.asyncio as aioredis

from backend.config import settings
from backend.db.pool import init_pool, close_pool, get_pool
from backend.providers.client import NeuroFlowClient
from pipelines.ingestion.extractors.extracted_page import ExtractedPage
from pipelines.ingestion.extractors.pdf_extractor import extract_pdf
from pipelines.ingestion.extractors.docx_extractor import extract_docx
from pipelines.ingestion.extractors.image_extractor import extract_image
from pipelines.ingestion.extractors.csv_extractor import extract_csv
from pipelines.ingestion.extractors.url_extractor import extract_url
from pipelines.ingestion.chunker import chunk_document, count_tokens

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

async def process_ingestion_task(task_payload: dict):
    """
    Main job processing pipeline:
    1. Update status to 'processing'.
    2. Decode base64 document bytes from Postgres (or fetch URL).
    3. Run file extractor.
    4. Run auto-selected chunking strategy.
    5. Generate embeddings and save chunks in a single SQL transaction.
    6. Update status to 'complete'.
    7. Emit OpenTelemetry span and log structured JSON.
    """
    doc_id = task_payload["document_id"]
    source_type = task_payload["source_type"]
    file_path = task_payload["file_path"]

    start_time = time.time()
    logger.info(f"Starting ingestion process for document {doc_id} ({source_type})")

    pool = get_pool()
    
    # 1. Update status to 'processing'
    async with pool.acquire() as conn:
        await conn.execute("UPDATE documents SET status = 'processing' WHERE id = $1", uuid.UUID(doc_id))
        doc_row = await conn.fetchrow("SELECT filename, metadata FROM documents WHERE id = $1", uuid.UUID(doc_id))

    if not doc_row:
        logger.error(f"Document {doc_id} not found in database.")
        return

    metadata = json.loads(doc_row["metadata"]) if doc_row["metadata"] else {}
    filename = doc_row["filename"]

    # 2. Extract pages
    pages = []
    try:
        if source_type == "url":
            url = metadata.get("url")
            pages = await extract_url(url)
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
                pages = [ExtractedPage(page_number=1, content=text_content, content_type="text", metadata={})]
    except Exception as e:
        logger.error(f"Extraction failed for document {doc_id}: {e}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))
        return

    page_count = len(pages)
    if page_count == 0:
        logger.error(f"No pages extracted for document {doc_id}.")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))
        return

    # 3. Chunk pages
    try:
        chunks = await chunk_document(pages, {"source_type": source_type, "filename": filename})
    except Exception as e:
        logger.error(f"Chunking failed for document {doc_id}: {e}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))
        return

    chunk_count = len(chunks)
    if chunk_count == 0:
        logger.error(f"No chunks generated for document {doc_id}.")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))
        return

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
                    token_count = count_tokens(content)
                    total_tokens += token_count
                    
                    # Generate embedding vector
                    embedding_calls += 1
                    vectors = await client.embed([content])
                    vector = vectors[0] if vectors else [0.0] * 1536
                    
                    # Merge metadata
                    chunk_meta = chunk.get("metadata", {})
                    parent_id = chunk.get("parent_id")
                    if parent_id:
                        chunk_meta["parent_id"] = parent_id

                    await conn.execute(
                        """
                        INSERT INTO chunks (id, document_id, content, embedding, chunk_index, token_count, metadata, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                        """,
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
        logger.info(f"Successfully processed document {doc_id} ({chunk_count} chunks, {total_tokens} tokens)")

        # 6. Observability: OpenTelemetry & JSON log
        if tracer:
            with tracer.start_as_current_span("ingestion.process") as span:
                span.set_attribute("document_id", doc_id)
                span.set_attribute("source_type", source_type)
                span.set_attribute("page_count", page_count)
                span.set_attribute("chunk_count", chunk_count)
                span.set_attribute("embedding_calls", embedding_calls)
                
        log_json = {
            "event": "ingestion_complete",
            "document_id": doc_id,
            "duration_ms": duration_ms,
            "chunks": chunk_count,
            "tokens": total_tokens
        }
        print(json.dumps(log_json))
        
    except Exception as e:
        logger.error(f"Failed to generate embeddings or save chunks: {e}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))

async def main():
    logger.info("Worker starting up...")
    
    # Initialize connection pool
    await init_pool(settings.database_url)
    
    logger.info("Worker is active and polling for jobs from Redis...")
    
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        while True:
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
