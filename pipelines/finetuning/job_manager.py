import asyncio
import uuid
import json
import redis.asyncio as aioredis
from backend.db.pool import get_pool
from backend.config import settings

async def mock_submit_and_poll_job(job_id: uuid.UUID, base_model: str, mlflow_run_id: str):  # type: ignore
    """
    Simulates sending a JSONL file to OpenAI and polling for completion.
    In a real app, this would call OpenAI's fine-tuning API.
    """
    # 1. Simulate waiting for the job to finish (Mock OpenAI processing time)
    await asyncio.sleep(5)
    
    # Fake OpenAI response data
    provider_job_id = f"ftjob-{str(job_id)[:8]}"
    mock_new_model_name = f"{base_model}:neuroflow:{str(job_id)[:8]}"
    
    pool = get_pool()
    
    # 2. Mark the job as successful in our database
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE finetune_jobs 
            SET status = 'succeeded', provider_job_id = $1, completed_at = NOW()
            WHERE id = $2
            """,
            provider_job_id, job_id
        )
    
    # 3. Register the new model in Redis so the Router can start using it immediately
    await register_model_in_redis(mock_new_model_name)
    
    # 4. Register in MLflow (Mocked connection)
    import mlflow
    mlflow.set_tracking_uri("http://mlflow:5000")
    mlflow.register_model(f"runs:/{mlflow_run_id}/model", f"neuroflow-finetune-{job_id}")
    
    print(f"Fine-tuning job {job_id} succeeded. Model registered as {mock_new_model_name}.")

async def register_model_in_redis(new_model_name: str):  # type: ignore
    """
    Appends the newly trained model to our global Redis model registry.
    """
    client = aioredis.from_url(settings.redis_url)
    
    # Get current models, or use empty list if none exist
    data = await client.get("router:models")
    if data:
        models = json.loads(data)
    else:
        models = []
        
    # Add the new model configuration
    models.append({
        "model_id": new_model_name,
        "provider": "openai",
        "input_cost_per_million": 3.00, # Fake cost for fine-tuned models
        "output_cost_per_million": 12.00,
        "context_window": 128000,
        "supports_vision": False,
        "supports_task_types": ["rag_generation"],
        "is_fine_tuned": True,
        "fine_tuned_for_task": "rag_generation"
    })
    
    # Save it back to Redis
    await client.set("router:models", json.dumps(models))
    await client.aclose()
