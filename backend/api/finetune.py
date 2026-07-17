import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.db.pool import get_pool
from pipelines.finetuning.extractor import extract_training_data
from pipelines.finetuning.job_manager import mock_submit_and_poll_job
from pipelines.finetuning.tracker import log_fine_tuning_run

router = APIRouter(prefix="/finetune", tags=["finetuning"])

class JobRequest(BaseModel):  # type: ignore
    base_model: str = "gpt-4o-mini"

@router.post("/jobs")  # type: ignore
async def create_finetuning_job(req: JobRequest, bg_tasks: BackgroundTasks):  # noqa: ANN201  # type: ignore
    """
    1. Extracts high-quality data.
    2. Logs the experiment to MLflow.
    3. Starts a background task to simulate OpenAI training.
    """
    job_id = uuid.uuid4()
    
    # 1. Extract valid training pairs
    jsonl_path = await extract_training_data(job_id)
    if not jsonl_path:
        raise HTTPException(status_code=400, detail="Not enough high-quality training pairs found.")
        
    # We estimate pairs by counting lines in the file
    with open(jsonl_path, encoding="utf-8") as f:  # noqa: ASYNC230
        pair_count = sum(1 for _ in f)

    # 2. Log to MLflow
    mlflow_run_id = log_fine_tuning_run(job_id, req.base_model, pair_count, jsonl_path)
    
    # 3. Create job record in the database
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO finetune_jobs (id, base_model, status, training_pair_count, mlflow_run_id)
            VALUES ($1, $2, 'pending', $3, $4)
            """,
            job_id, req.base_model, pair_count, mlflow_run_id
        )
        
    # 4. Trigger background training job
    bg_tasks.add_task(mock_submit_and_poll_job, job_id, req.base_model, mlflow_run_id)
    
    return {"job_id": str(job_id), "status": "started", "message": "Extraction complete, training simulating in background."}  # noqa: E501

@router.get("/jobs")
async def list_jobs():  # noqa: ANN201  # type: ignore
    """Returns a list of all fine-tuning jobs."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM finetune_jobs ORDER BY created_at DESC")
        return [dict(r) for r in rows]

@router.get("/jobs/{job_id}")  # type: ignore
async def get_job_status(job_id: uuid.UUID):  # noqa: ANN201  # type: ignore
    """Returns the status and details of a specific job."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM finetune_jobs WHERE id = $1", job_id)
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(row)

@router.get("/training-data/preview")
async def preview_training_data():  # noqa: ANN201  # type: ignore
    """
    Shows a sample of what the extractor WOULD pull, without actually starting a job.
    Very useful for debugging and quality inspection.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Simple DB query to peek at top 5 qualifying pairs
        rows = await conn.fetch("""
            SELECT tp.system_prompt, tp.user_message, tp.assistant_message
            FROM training_pairs tp
            JOIN evaluations e ON tp.run_id = e.run_id
            WHERE tp.quality_score >= 0.82 
            AND e.faithfulness > 0.8
            LIMIT 5
        """)
        return [dict(r) for r in rows]
