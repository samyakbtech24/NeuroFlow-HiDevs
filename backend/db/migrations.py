import os
import logging
import asyncio
import asyncpg
from backend.db.pool import get_pool
from backend.config import settings

logger = logging.getLogger(__name__)

async def ensure_mlflow_db(dsn: str) -> None:
    """
    Connects to the server and ensures that the 'mlflow' database exists.
    If it does not exist, creates it. Includes a retry loop to wait for PG server.
    """
    conn = None
    retries = 15
    delay = 2.0
    for attempt in range(1, retries + 1):
        try:
            conn = await asyncpg.connect(dsn)
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'mlflow'")
            if not exists:
                logger.info("Database 'mlflow' does not exist. Creating it now...")
                # Note: CREATE DATABASE cannot run inside a transaction block.
                await conn.execute("CREATE DATABASE mlflow")
                logger.info("Database 'mlflow' created successfully.")
            else:
                logger.debug("Database 'mlflow' already exists.")
            break
        except Exception as e:
            if attempt == retries:
                logger.error(f"Failed to check/create 'mlflow' database after {retries} attempts: {e}")
                raise
            logger.warning(f"Database check for 'mlflow' database failed on attempt {attempt}/{retries}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        finally:
            if conn:
                await conn.close()
                conn = None


async def check_schema_applied() -> bool:
    """
    Verifies if the schema is applied by checking if the primary
    tables are already registered in the 'public' schema.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_name IN ('documents', 'chunks', 'pipelines', 'pipeline_runs');
            """)
            # Expecting all 4 critical tables to be present
            return len(tables) >= 4
    except Exception as e:
        logger.error(f"Error checking if schema is applied: {e}")
        return False

async def ensure_evaluations_metadata_column() -> None:
    """
    Dynamically ensures the 'metadata' JSONB column exists in the 'evaluations' table
    to store human feedback calibration flagging.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'"
            )
            logger.info("Ensured 'metadata' column exists in 'evaluations' table.")
    except Exception as e:
        logger.error(f"Error ensuring evaluations metadata column: {e}")

async def ensure_pipeline_versioning_schema() -> None:
    """
    Dynamically applies additive schema changes for Task 8: Named Pipeline System.
    Adds version/status to pipelines, creates pipeline_versions, and updates pipeline_runs.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            # 1. Add version and status to pipelines
            await conn.execute("ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1")
            await conn.execute("ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'")
            
            # 2. Create pipeline_versions for immutable audit trail
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_versions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
                    version INT NOT NULL,
                    config JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(pipeline_id, version)
                )
            """)
            
            # 3. Add pipeline_version to pipeline_runs
            await conn.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS pipeline_version INT")
            
            logger.info("Ensured pipeline versioning schema is applied.")
    except Exception as e:
        logger.error(f"Error ensuring pipeline versioning schema: {e}")

async def apply_migrations(schema_path: str = "../infra/init/001_schema.sql") -> None:
    """
    Applies the schema file if tables do not exist, and runs schema updates.
    """
    # Always run the dynamic schema additions on startup
    await ensure_evaluations_metadata_column()
    await ensure_pipeline_versioning_schema()
    if await check_schema_applied():
        logger.info("Database schema is already applied. Skipping migrations.")
        return

    logger.info("Schema not found or incomplete. Applying database migrations...")
    
    # Try finding the file relative to current directory if default path doesn't exist
    if not os.path.exists(schema_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        schema_path = os.path.join(base_dir, "infra", "init", "001_schema.sql")

    if not os.path.exists(schema_path):
        # In Docker, migrations are often pre-applied by the docker-entrypoint-initdb.d folder mount,
        # but if the file is not found, we throw a descriptive error.
        raise FileNotFoundError(
            f"Schema SQL file not found at: {schema_path}. "
            "Please ensure that the infra directory exists or migrations are pre-applied."
        )

    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    pool = get_pool()
    async with pool.acquire() as conn:
        logger.info("Executing 001_schema.sql migration...")
        # Connection.execute() can execute multiple SQL statements separated by semicolons
        await conn.execute(sql_content)
        logger.info("Schema migration executed successfully.")
