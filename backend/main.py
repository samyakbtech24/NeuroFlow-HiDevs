import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from backend.config import settings
from backend.db.pool import init_pool, close_pool
from backend.db.migrations import ensure_mlflow_db, apply_migrations
from backend.db.health import check_postgres, check_redis, check_mlflow
from backend.api.ingest import router as ingest_router
from backend.api.query import router as query_router
from backend.api.pipelines import router as pipelines_router
from backend.api.compare import router as compare_router

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neuroflow-api")

# Set up OpenTelemetry Tracing Setup
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    logger.warning("OpenTelemetry packages not available. Tracing is disabled.")

def setup_otlp(app: FastAPI):
    """
    Configures OpenTelemetry TracerProvider, hooks up OTLP exporter,
    and instruments the FastAPI application with the ASGI middleware.
    """
    if not HAS_OTEL:
        return
    try:
        resource = Resource.create(attributes={"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        # OTLPSpanExporter exports traces to Jaeger (default http://jaeger:4317)
        processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        # OpenTelemetry ASGI middleware instrumentation for FastAPI
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry FastAPI middleware instrumentation applied successfully.")
    except Exception as e:
        logger.error(f"Failed to apply OpenTelemetry instrumentation: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager that handles startup tasks (ensuring mlflow DB, 
    initializing connection pool, applying schema) and shutdown tasks (closing pool).
    """
    # 1. Startup: Pre-flight check/creation of the 'mlflow' database
    await ensure_mlflow_db(settings.database_url)
    
    # 2. Startup: Initialize the database pool
    await init_pool(settings.database_url)
    
    # 3. Startup: Run migrations if schema does not exist
    await apply_migrations()
    
    # 4. Startup: Setup OTLP Tracing
    setup_otlp(app)
    
    logger.info("Application startup phase completed.")
    yield
    
    # 5. Shutdown: Close the database pool
    await close_pool()
    logger.info("Application shutdown phase completed.")

app = FastAPI(
    title="NeuroFlow API",
    description="Backend API Foundation for NeuroFlow RAG Subsystem",
    version="1.0.0",
    lifespan=lifespan
)

# Register Ingestion API endpoints
app.include_router(ingest_router)

# Register Query API endpoints
app.include_router(query_router)

# Register Pipeline System endpoints
app.include_router(pipelines_router)
app.include_router(compare_router)

@app.get("/health")
async def health(response: Response):
    """
    Retrieves health status of Postgres, Redis, and MLflow connections.
    """
    postgres_ok = await check_postgres()
    redis_ok = await check_redis()
    mlflow_ok = await check_mlflow()
    
    all_ok = postgres_ok and redis_ok and mlflow_ok
    status = "ok" if all_ok else "error"
    
    if not all_ok:
        response.status_code = 503
        
    return {
        "status": status,
        "checks": {
            "postgres": postgres_ok,
            "redis": redis_ok,
            "mlflow": mlflow_ok
        }
    }

@app.get("/metrics")
async def metrics():
    """
    Exposes metrics in a Prometheus-compatible text format.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
