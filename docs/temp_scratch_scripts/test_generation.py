import asyncio
import json
import logging
import os
import sys
import uuid

import httpx
import redis.asyncio as aioredis

# Add parent directory to path to allow importing packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import settings
from backend.db.pool import close_pool, get_pool, init_pool

# Override hosts to localhost if running on host machine outside docker container
if not os.path.exists("/.dockerenv"):
    settings.postgres_host = "localhost"
    settings.redis_host = "localhost"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test-generation")

async def verify_database_and_redis(run_id: uuid.UUID) -> None:
    print("\n--- 3. Verifying Database Run Log and Redis Queue ---")
    pool = get_pool()
    
    # Check Postgres Pipeline Run
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, pipeline_id, query, retrieved_chunk_ids, generation, status, model_used, latency_ms 
            FROM pipeline_runs 
            WHERE id = $1
            """,  # noqa: E501
            run_id
        )
        
    assert row is not None, "pipeline_runs row should exist in database"
    print("Postgres run log found:")
    print(f"  Query:        '{row['query']}'")
    print(f"  Status:       '{row['status']}'")
    print(f"  Model Used:   '{row['model_used']}'")
    print(f"  Latency:       {row['latency_ms']}ms")
    print(f"  Chunks Cited:  {len(row['retrieved_chunk_ids'])} chunks")
    assert row["status"] == "complete", "Database run status should be updated to 'complete'"
    assert row["generation"] != "", "Database run generation column should be populated"
    
    # Check Redis Eval Queue
    redis_client = aioredis.from_url(settings.redis_url)
    queue_len = await redis_client.llen("queue:eval")
    print(f"Redis 'queue:eval' length: {queue_len}")
    
    if queue_len > 0:
        # Pop the latest item (or just examine it without removing if possible, but pop is fine for test verification)  # noqa: E501
        item_bytes = await redis_client.rpop("queue:eval")
        if item_bytes:
            payload = json.loads(item_bytes.decode("utf-8"))
            print(f"Redis queued job payload: {payload}")
            assert payload["run_id"] == str(run_id), "Queued job run_id should match the execution run_id"  # noqa: E501
            print("Redis evaluation trigger verified successfully!")
            
    await redis_client.aclose()

async def test_streaming_pipeline() -> None:
    # Make sure we use a valid pipeline_id
    pipeline_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    
    # Clear Redis test queue for isolation
    redis_test_client = aioredis.from_url(settings.redis_url)
    await redis_test_client.delete("queue:eval")
    await redis_test_client.aclose()
    
    # Initialize DB pool to insert dummy pipeline if needed
    await init_pool(settings.database_url)
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pipelines (id, name, config, created_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            pipeline_id,
            "Default-Test-Pipeline",
            json.dumps({"model": "gpt-4o-mini", "temperature": 0.0})
        )
    
    url = "http://localhost:8000/query"
    query_text = "What is Hierarchical Navigable Small World HNSW graphs?"
    
    # 1. Trigger POST /query
    print("\n--- 1. Testing POST /query endpoint (Stream Initializer) ---")
    async with httpx.AsyncClient() as client:
        payload = {
            "query": query_text,
            "pipeline_id": str(pipeline_id),
            "stream": True
        }
        print(f"Calling POST {url} with query: '{query_text}'")
        resp = await client.post(url, json=payload)
        print(f"POST Response Code: {resp.status_code}")
        print(f"POST Response Body: {resp.text}")
        assert resp.status_code == 200, "POST /query request should succeed"
        
        run_data = resp.json()
        run_id = uuid.UUID(run_data["run_id"])
        
        # 2. Test GET /query/{run_id}/stream (SSE Endpoint)
        print("\n--- 2. Testing GET /query/{run_id}/stream SSE Endpoint ---")
        stream_url = f"http://localhost:8000/query/{run_id}/stream"
        print(f"Connecting to SSE EventSource stream: {stream_url}")
        
        events_received = []
        tokens = []
        citations = []
        
        # We read the HTTP stream progressively
        async with client.stream("GET", stream_url, timeout=30.0) as stream_resp:
            assert stream_resp.status_code == 200, "SSE connection should open successfully"
            
            # Read line by line
            async for line in stream_resp.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    # Extract JSON payload
                    data_json = line[len("data:"):].strip()
                    try:
                        event = json.loads(data_json)
                        events_received.append(event)
                        etype = event.get("type")
                        
                        if etype == "retrieval_start":
                            print("Event: [retrieval_start]")
                        elif etype == "retrieval_complete":
                            print(f"Event: [retrieval_complete] - {event['chunk_count']} chunks found from: {event['sources']}")  # noqa: E501
                        elif etype == "token":
                            # Stream tokens progressively on same line
                            sys.stdout.write(event["delta"])
                            sys.stdout.flush()
                            tokens.append(event["delta"])
                        elif etype == "done":
                            print("\nEvent: [done]")
                            citations = event.get("citations", [])
                            print(f"Citations resolved: {citations}")
                    except Exception as parse_err:
                        print(f"\nFailed to parse event line: {line} ({parse_err})")
                        
        print("\nSSE stream completed!")
        
        # Assertions
        assert len(events_received) >= 4, "Should receive at least retrieval_start, retrieval_complete, token, and done events"  # noqa: E501
        assert len(tokens) > 0, "Should receive token events"
        assert len(citations) > 0, "Should resolve at least 1 citation for seeded content matching query"  # noqa: E501
        print(f"First Citation Document: '{citations[0]['document']}'")
        assert citations[0]["invalid_citation"] is False, "Citation should be valid"
        
        # Wait a brief moment to allow background Redis tasks to execute
        await asyncio.sleep(1)
        
        # Verify db updates and redis enqueuing
        await verify_database_and_redis(run_id)
        
    await close_pool()

if __name__ == "__main__":
    asyncio.run(test_streaming_pipeline())
