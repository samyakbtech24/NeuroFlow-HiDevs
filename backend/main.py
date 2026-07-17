import logging
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.auth import router as auth_router
from backend.api.compare import router as compare_router
from backend.api.evaluations import router as evaluations_router
from backend.api.finetune import router as finetune_router
from backend.api.ingest import router as ingest_router
from backend.api.pipelines import router as pipelines_router
from backend.api.query import router as query_router
from backend.config import settings
from backend.db.health import check_mlflow, check_postgres, check_redis
from backend.db.migrations import apply_migrations, ensure_mlflow_db
from backend.db.pool import close_pool, init_pool
from backend.security.auth import get_current_user, require_scope

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neuroflow-api")

# Set up OpenTelemetry Tracing Setup
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    logger.warning("OpenTelemetry packages not available. Tracing is disabled.")

def setup_otlp(app: FastAPI) -> None:
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
async def lifespan(app: FastAPI):  # noqa: ANN201  # type: ignore
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):  # type: ignore
    async def dispatch(self, request, call_next):  # noqa: ANN001, ANN201  # type: ignore
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Register Auth endpoints
app.include_router(auth_router)  # noqa: F821  # type: ignore

# Register Ingestion API endpoints
app.include_router(ingest_router, dependencies=[Depends(get_current_user), Depends(require_scope("ingest"))])  # noqa: E501, F821  # type: ignore

# Register Query API endpoints
app.include_router(query_router, dependencies=[Depends(get_current_user), Depends(require_scope("query"))])  # noqa: E501, F821  # type: ignore

# Register Pipeline System endpoints
app.include_router(pipelines_router, dependencies=[Depends(get_current_user), Depends(require_scope("admin"))])  # noqa: E501, F821  # type: ignore
app.include_router(compare_router, dependencies=[Depends(get_current_user), Depends(require_scope("query"))])  # noqa: E501, F821  # type: ignore
app.include_router(finetune_router, dependencies=[Depends(get_current_user), Depends(require_scope("admin"))])  # noqa: E501, F821  # type: ignore
app.include_router(evaluations_router, dependencies=[Depends(get_current_user), Depends(require_scope("query"))])  # noqa: E501, F821  # type: ignore

@app.get("/health")  # type: ignore
async def health(response: Response):  # noqa: ANN201  # type: ignore
    """
    Retrieves health status of core services and resilience systems (Circuit Breakers, Queues).
    """
    postgres = await check_postgres()
    redis = await check_redis()
    mlflow = await check_mlflow()
    
    # 1. Check Circuit Breakers dynamically
    circuit_breakers = {}
    any_open = False
    
    if redis["status"] == "ok":
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            # Scan for all circuit breaker state keys
            async for key in client.scan_iter("circuit:*:state"):
                name = key.split(":")[1]
                state = await client.get(key)
                
                if state == "open":
                    any_open = True
                    opened_at = await client.get(f"circuit:{name}:opened_at")
                    circuit_breakers[name] = {"state": "open", "opened_at": opened_at}
                else:
                    failures = await client.get(f"circuit:{name}:failure_count") or 0
                    circuit_breakers[name] = {"state": state, "failure_count": int(failures)}
            
            # 2. Check Queue Depths
            queue_depth = await client.llen("queue:ingest")
        finally:
            await client.aclose()
    else:
        queue_depth = 0
        
    # Determine final system status
    critical = postgres["status"] != "ok" or redis["status"] != "ok"
    
    if critical:
        status = "critical"
        response.status_code = 503
    elif any_open:
        status = "degraded"
        # Often degraded APIs still return 200 so monitoring knows the API itself is reachable,
        # but you can return 200 or 503 depending on corporate standards.
    else:
        status = "ok"
        
    return {
        "status": status,
        "checks": {
            "postgres": postgres,
            "redis": redis,
            "mlflow": mlflow,
            "circuit_breakers": circuit_breakers,
            "queue_depth": queue_depth,
            "worker_count": 2  # Hardcoded for the 2 workers in our docker-compose
        }
    }

@app.get("/metrics")
async def metrics():  # noqa: ANN201  # type: ignore
    """
    Exposes metrics in a Prometheus-compatible text format.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
