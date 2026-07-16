from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID
import json
from pydantic import BaseModel
from backend.db.pool import get_pool
from backend.models.pipeline import PipelineConfig
import asyncpg
from backend.security.validators import sanitize_text

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

class PipelineResponse(BaseModel):
    id: UUID
    name: str
    config: PipelineConfig
    version: int
    status: str
    created_at: str

@router.post("", response_model=Dict[str, Any])
async def create_pipeline(config: PipelineConfig):
    """
    Creates a new pipeline, validating the schema strictly.
    """
    config.name = sanitize_text(config.name)
    if len(config.name) > 100:
        raise HTTPException(status_code=400, detail="Pipeline name exceeds maximum length of 100 characters.")
        
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Check if pipeline with this name already exists
                existing = await conn.fetchrow("SELECT id FROM pipelines WHERE name = $1", config.name)
                if existing:
                    raise HTTPException(status_code=400, detail="Pipeline with this name already exists.")

                config_json = config.model_dump_json()
                
                # Insert into main table
                row = await conn.fetchrow(
                    """
                    INSERT INTO pipelines (name, config, version, status) 
                    VALUES ($1, $2::jsonb, 1, 'active') 
                    RETURNING id
                    """,
                    config.name, config_json
                )
                pipeline_id = row['id']
                
                # Insert into history table
                await conn.execute(
                    """
                    INSERT INTO pipeline_versions (pipeline_id, version, config)
                    VALUES ($1, 1, $2::jsonb)
                    """,
                    pipeline_id, config_json
                )
                
                return {"pipeline_id": pipeline_id, "status": "created", "version": 1}
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Pipeline with this name already exists.")

@router.get("", response_model=List[Dict[str, Any]])
async def list_pipelines():
    """
    Lists all active pipelines with their latest config and aggregate evaluation scores.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id, p.name, p.config, p.version, p.created_at,
                   COUNT(pr.id) as total_runs,
                   AVG(e.overall_score) as avg_score
            FROM pipelines p
            LEFT JOIN pipeline_runs pr ON p.id = pr.pipeline_id
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE p.status = 'active'
            GROUP BY p.id, p.name, p.config, p.version, p.created_at
            ORDER BY p.created_at DESC
            """
        )
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "config": json.loads(r["config"]),
                "version": r["version"],
                "created_at": str(r["created_at"]),
                "total_runs": r["total_runs"],
                "avg_score": r["avg_score"] if r["avg_score"] is not None else None
            }
            for r in rows
        ]

@router.get("/{pipeline_id}", response_model=Dict[str, Any])
async def get_pipeline(pipeline_id: UUID):
    """
    Returns full config and aggregate evaluation scores for a specific pipeline.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM pipelines WHERE id = $1 AND status != 'archived'", pipeline_id)
        if not row:
            raise HTTPException(status_code=404, detail="Pipeline not found")
            
        scores = await conn.fetchrow(
            """
            SELECT AVG(faithfulness) as avg_faithfulness,
                   AVG(answer_relevance) as avg_relevance,
                   AVG(context_precision) as avg_precision,
                   AVG(context_recall) as avg_recall
            FROM evaluations e
            JOIN pipeline_runs pr ON e.run_id = pr.id
            WHERE pr.pipeline_id = $1
            """,
            pipeline_id
        )
            
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "config": json.loads(row["config"]),
            "version": row["version"],
            "created_at": str(row["created_at"]),
            "metrics": dict(scores) if scores else {}
        }

@router.patch("/{pipeline_id}", response_model=Dict[str, Any])
async def update_pipeline(pipeline_id: UUID, config: PipelineConfig):
    """
    Updates a pipeline's config. Creates a new version while preserving the old one.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT id, name, version FROM pipelines WHERE id = $1 AND status != 'archived'", pipeline_id)
            if not row:
                raise HTTPException(status_code=404, detail="Pipeline not found")
                
            if config.name != row["name"]:
                # Ensure the new name doesn't conflict
                existing = await conn.fetchrow("SELECT id FROM pipelines WHERE name = $1 AND id != $2", config.name, pipeline_id)
                if existing:
                    raise HTTPException(status_code=400, detail="Pipeline name already exists")
            
            new_version = row["version"] + 1
            config_json = config.model_dump_json()
            
            # Update main pipelines table (additive updates only)
            await conn.execute(
                """
                UPDATE pipelines 
                SET config = $1::jsonb, version = $2, name = $3
                WHERE id = $4
                """,
                config_json, new_version, config.name, pipeline_id
            )
            
            # Insert historical snapshot
            await conn.execute(
                """
                INSERT INTO pipeline_versions (pipeline_id, version, config)
                VALUES ($1, $2, $3::jsonb)
                """,
                pipeline_id, new_version, config_json
            )
            
            return {"pipeline_id": pipeline_id, "status": "updated", "new_version": new_version}

@router.delete("/{pipeline_id}")
async def delete_pipeline(pipeline_id: UUID):
    """
    Soft deletes a pipeline by setting status='archived'.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("UPDATE pipelines SET status = 'archived' WHERE id = $1", pipeline_id)
        if res == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"status": "archived"}

@router.get("/{pipeline_id}/runs")
async def get_pipeline_runs(pipeline_id: UUID, limit: int = 50, offset: int = 0):
    """
    Paginated list of runs for a pipeline with latency, tokens, and eval scores.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pr.id, pr.query, pr.pipeline_version, pr.latency_ms, 
                   pr.input_tokens, pr.output_tokens, pr.created_at,
                   e.overall_score
            FROM pipeline_runs pr
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE pr.pipeline_id = $1
            ORDER BY pr.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            pipeline_id, limit, offset
        )
        return [dict(r) for r in rows]

@router.get("/{pipeline_id}/analytics")
async def get_pipeline_analytics(pipeline_id: UUID):
    """
    Aggregate statistics including p50, p95, p99 latencies.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY pr.latency_ms) as p50_latency,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY pr.latency_ms) as p95_latency,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY pr.latency_ms) as p99_latency,
                AVG(pr.latency_ms) as avg_latency,
                COUNT(pr.id) as total_runs,
                AVG(e.faithfulness) as avg_faithfulness,
                AVG(e.overall_score) as avg_score
            FROM pipeline_runs pr
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE pr.pipeline_id = $1
            """,
            pipeline_id
        )
        if not row or row["total_runs"] == 0:
            return {"detail": "No run data available for analytics."}
            
        return dict(row)
