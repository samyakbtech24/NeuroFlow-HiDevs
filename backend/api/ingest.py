import base64
import hashlib
import json
import logging
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.config import settings
from backend.db.pool import get_pool
from backend.resilience.backpressure import check_ingestion_backpressure
from backend.resilience.rate_limiter import rate_limiter
from backend.security.validators import validate_file_bytes, validate_url

logger = logging.getLogger("ingest-api")
router = APIRouter()

@router.post("/", status_code=202)  # type: ignore
async def ingest_document(  # noqa: ANN201  # type: ignore
    request: Request,
    file: UploadFile | None = File(None),
    url: str | None = Form(None)
):
    """
    Accepts multipart/form-data with file or JSON with url.
    Checks deduplication, inserts queued document record, and enqueues job in Redis.
    """
    # 0. Resilience Checks
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check_sliding_window(f"ingest_api:{client_ip}", limit=10, window_seconds=3600)  # noqa: E501
    backpressure_warning = await check_ingestion_backpressure()  # type: ignore

    # 1. Check if request is JSON body containing url
    if not file and not url:
        try:
            body = await request.json()
            url = body.get("url")
        except Exception:
            pass

    if not file and not url:
        raise HTTPException(status_code=400, detail="Either file or url must be provided.")
        
    if url:
        validate_url(url)

    file_bytes = b""
    filename = ""
    source_type = ""

    if file:
        file_bytes = await file.read()
        if len(file_bytes) > 100 * 1024 * 1024:  # 100MB limit
            raise HTTPException(status_code=413, detail="File too large (Max 100MB).")
        filename = file.filename or "uploaded_file"
        
        # File type security check using magic bytes
        validate_file_bytes(file_bytes, filename, file.content_type)
        
        # Determine source_type from extension
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext == "pdf":
            source_type = "pdf"
        elif ext == "docx":
            source_type = "docx"
        elif ext in ("jpg", "jpeg", "png", "webp"):
            source_type = "image"
        elif ext == "csv":
            source_type = "csv"
        else:
            source_type = "text"
    else:
        filename = url  # type: ignore
        source_type = "url"
        file_bytes = url.encode("utf-8")  # type: ignore

    # 2. Compute SHA-256 content hash
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # 3. Deduplication Check
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM documents WHERE content_hash = $1",
            content_hash
        )
        if existing:
            logger.info(f"Duplicate document found with ID: {existing['id']}")
            return {
                "document_id": str(existing["id"]),
                "status": existing["status"],
                "duplicate": True
            }

    # 4. Insert queued document and enqueue task
    doc_id = str(uuid.uuid4())
    
    # Store file content base64 encoded in metadata to make it shared-accessible
    metadata = {}
    if file:
        metadata = {
            "file_content_base64": base64.b64encode(file_bytes).decode("utf-8"),
            "filename": filename
        }
    else:
        metadata = {
            "url": url  # type: ignore
        }

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, filename, source_type, content_hash, metadata, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'queued', NOW())
            """,  # noqa: E501
            uuid.UUID(doc_id),
            filename,
            source_type,
            content_hash,
            json.dumps(metadata)
        )

    # Push job details to Redis queue
    try:
        redis_client = aioredis.from_url(settings.redis_url, socket_timeout=2.0)
        payload = {
            "document_id": doc_id,
            "file_path": filename,
            "source_type": source_type
        }
        await redis_client.lpush("queue:ingest", json.dumps(payload))
        await redis_client.aclose()
        logger.info(f"Enqueued document {doc_id} to Redis 'queue:ingest'")
    except Exception as e:
        logger.error(f"Failed to enqueue to Redis: {e}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", uuid.UUID(doc_id))  # noqa: E501
        raise HTTPException(status_code=500, detail="Failed to enqueue ingestion task.")

    response_payload = {
        "document_id": doc_id,
        "status": "queued",
        "duplicate": False
    }
    
    # Merge backpressure warning if present
    # We call check_ingestion_backpressure() at the start of the function, 
    # but since python's scoping allows us to use it here, we will store its result.
    if backpressure_warning:
        response_payload.update(backpressure_warning)
        
    return response_payload

@router.get("/documents/{document_id}")  # type: ignore
async def get_document_status(document_id: str):  # noqa: ANN201  # type: ignore
    """
    Returns document status, chunk count, and metadata.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document UUID format.")

    pool = get_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT id, filename, source_type, status, chunk_count, metadata FROM documents WHERE id = $1",  # noqa: E501
            doc_uuid
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
            
        metadata_clean = json.loads(doc["metadata"]) if doc["metadata"] else {}
        # Remove base64 content to keep return payload clean
        metadata_clean.pop("file_content_base64", None)
        
        return {
            "document_id": str(doc["id"]),
            "filename": doc["filename"],
            "source_type": doc["source_type"],
            "status": doc["status"],
            "chunk_count": doc["chunk_count"],
            "metadata": metadata_clean
        }

@router.get("", response_model=list[dict[str, Any]])
async def list_documents():  # noqa: ANN201  # type: ignore
    """
    Returns a list of all ingested documents, ordered by creation date.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, filename, source_type, status, chunk_count, created_at FROM documents ORDER BY created_at DESC LIMIT 100"  # noqa: E501
        )
        return [
            {
                "id": str(doc["id"]),
                "filename": doc["filename"],
                "source_type": doc["source_type"],
                "status": doc["status"],
                "chunk_count": doc["chunk_count"],
                "created_at": str(doc["created_at"])
            }
            for doc in rows
        ]
