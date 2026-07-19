import asyncio
import json
import os
import sys
import uuid

import httpx

# Add parent directory to path to allow importing packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import settings
from backend.db.pool import close_pool, get_pool, init_pool
from evaluation.judge import EvaluationJudge

# Override hosts to localhost if running on host machine outside docker container
if not os.path.exists("/.dockerenv"):
    settings.postgres_host = "localhost"
    settings.redis_host = "localhost"

async def test_evaluation_judge_flow() -> None:
    # 1. Initialize DB pool
    print("\n--- 1. Initializing DB Connection Pool ---")
    await init_pool(settings.database_url)
    pool = get_pool()
    
    # 2. Insert dummy references to satisfy foreign keys
    print("\n--- 2. Setting Up Test Reference Rows in PostgreSQL ---")
    pipeline_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    run_id = uuid.uuid4()
    chunk_id = uuid.UUID("c0000001-0000-0000-0000-000000000001")
    
    async with pool.acquire() as conn:
        # Seed pipeline
        await conn.execute(
            """
            INSERT INTO pipelines (id, name, config, created_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            pipeline_id,
            "Evaluation-Test-Pipeline",
            json.dumps({"model": "gpt-4o-mini", "temperature": 0.0})
        )
        
        # Seed chunk if it doesn't exist
        await conn.execute(
            """
            INSERT INTO chunks (id, document_id, content, embedding, chunk_index, token_count, metadata)
            VALUES ($1, $2, 'Hierarchical Navigable Small World HNSW graphs are state of the art indexing.', $3::float4[], 0, 10, '{}')
            ON CONFLICT (id) DO NOTHING
            """,  # noqa: E501
            chunk_id,
            uuid.uuid4(),
            [0.1] * 1536
        )
        
        # Seed pipeline run
        await conn.execute(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, query, retrieved_chunk_ids, generation, status, created_at)
            VALUES ($1, $2, 'What is HNSW?', $3, 'HNSW are hierarchical navigable small world graphs.', 'complete', NOW())
            """,  # noqa: E501
            run_id,
            pipeline_id,
            [chunk_id]
        )
        
    print(f"Created Test pipeline_runs Row: {run_id}")

    # 3. Test EvaluationJudge class run
    print("\n--- 3. Testing EvaluationJudge Automated Run ---")
    judge = EvaluationJudge()
    res = await judge.evaluate_run(run_id)
    print(f"Judge evaluation outcome: {res}")
    assert res["overall_score"] is not None, "Evaluation overall_score should be calculated"
    
    # Verify evaluations row in PostgreSQL
    async with pool.acquire() as conn:
        eval_row = await conn.fetchrow(
            "SELECT faithfulness, answer_relevance, context_precision, context_recall, overall_score, metadata FROM evaluations WHERE run_id = $1",  # noqa: E501
            run_id
        )
    print(f"Postgres evaluations table row: {eval_row}")
    assert eval_row is not None, "evaluations row should be logged in database"
    assert eval_row["overall_score"] == res["overall_score"]

    # 4. Test Human Feedback PATCH rating endpoint
    print("\n--- 4. Testing PATCH /runs/{run_id}/rating Route ---")
    url = f"http://localhost:8000/runs/{run_id}/rating"
    async with httpx.AsyncClient() as client:
        # Send user rating 1 star (causing significant misalignment, should flag calibration_needed)
        payload = {"rating": 1}
        print(f"Calling PATCH {url} with rating 1 (Expect calibration_needed = True)")
        resp = await client.patch(url, json=payload)
        print(f"PATCH Response Code: {resp.status_code}")
        print(f"PATCH Response Body: {resp.text}")
        assert resp.status_code == 200, "PATCH rating request should succeed"
        
        resp_data = resp.json()
        assert resp_data["calibration_needed"] is True, "Large rating gap should flag calibration_needed = True"  # noqa: E501

        # Verify evaluations table has been updated
        async with pool.acquire() as conn:
            updated_eval_row = await conn.fetchrow(
                "SELECT user_rating, metadata FROM evaluations WHERE run_id = $1",
                run_id
            )
        print(f"Postgres evaluations table after PATCH: {updated_eval_row}")
        assert updated_eval_row["user_rating"] == 1
        meta = json.loads(updated_eval_row["metadata"])
        assert meta["calibration_needed"] is True

    print("\nAll Evaluation Judge Integration Tests PASSED successfully!")
    await close_pool()

if __name__ == "__main__":
    asyncio.run(test_evaluation_judge_flow())
