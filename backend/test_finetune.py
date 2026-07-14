import asyncio
import httpx
import json
import time
import uuid
from backend.db.pool import get_pool, init_pool
from backend.config import settings

async def seed_db():
    print("Seeding database with 10 qualifying training pairs...")
    pool = get_pool()
    async with pool.acquire() as conn:
        # Create a dummy pipeline to satisfy foreign key constraints
        await conn.execute("INSERT INTO pipelines (id, name, config) VALUES ('00000000-0000-0000-0000-000000000000', 'mock-finetune', '{}') ON CONFLICT DO NOTHING")
        
        for i in range(10):
            run_id = uuid.uuid4()
            # 1. Insert fake pipeline_run
            await conn.execute(
                "INSERT INTO pipeline_runs (id, pipeline_id, query) VALUES ($1, '00000000-0000-0000-0000-000000000000', 'test query')",
                run_id
            )
            # 2. Insert fake evaluation with high scores
            await conn.execute(
                "INSERT INTO evaluations (run_id, faithfulness, user_rating) VALUES ($1, 0.95, 5)",
                run_id
            )
            # 3. Insert training pair (between 50-2000 chars and has [Source 1])
            await conn.execute(
                """
                INSERT INTO training_pairs (run_id, user_message, assistant_message, quality_score)
                VALUES ($1, 'What is the refund policy?', 'According to the company handbook [Source 1], the refund policy is exactly 30 days. This response is intentionally made a bit longer so that it passes the 50 token (approx 200 character) minimum length requirement for the fine tuning extractor. Thank you.', 0.9)
                """,
                run_id
            )

async def test_finetune():
    print("Testing Fine-Tuning Pipeline (Mock Mode)...")
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # 1. Preview training data
        print("\n--- Previewing Extraction Data ---")
        preview = await client.get("/finetune/training-data/preview")
        print(f"Found {len(preview.json())} qualifying pairs.")
        
        # 2. Trigger a fine-tuning job
        print("\n--- Submitting Fine-Tuning Job ---")
        res = await client.post("/finetune/jobs", json={"base_model": "gpt-4o-mini"})
        print(res.text)
        
        if res.status_code != 200:
            print("Failed to start job. (Maybe DB is empty? Need to seed pairs first).")
            return
            
        job_id = res.json()["job_id"]
        
        # 3. Poll for background completion
        print("\n--- Polling Job Status ---")
        for _ in range(10):
            status_res = await client.get(f"/finetune/jobs/{job_id}")
            data = status_res.json()
            print(f"Status: {data['status']}")
            
            if data['status'] == 'succeeded':
                print(f"Success! Provider Job ID: {data['provider_job_id']}")
                break
                
            await asyncio.sleep(1)

async def main():
    await init_pool(settings.database_url)
    await seed_db()
    await test_finetune()

if __name__ == "__main__":
    asyncio.run(main())
