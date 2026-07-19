from collections.abc import AsyncGenerator
from pathlib import Path

from .models import Document, EvaluationResult, QueryResult


class NeuroFlowClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        
    async def ingest_file(self, file_path: str | Path, pipeline_id: str = None) -> Document:
        """Upload and ingest a file. Waits for ingestion to complete."""
        # Simulated implementation mapping API
        return Document(id="doc-123", status="complete")

    async def ingest_url(self, url: str, pipeline_id: str = None) -> Document:
        """Ingest a URL. Waits for ingestion to complete."""
        return Document(id="doc-456", status="complete")

    async def query(self, query: str, pipeline_id: str, stream: bool = False) -> QueryResult | AsyncGenerator:
        """Run a RAG query. If stream=True, returns an async generator of tokens."""
        if stream:
            async def mock_stream():
                for token in ["This", " is", " a", " test", " stream."]:
                    yield token
            return mock_stream()
        return QueryResult(answer="Mock response.", sources=[])

    async def get_evaluation(self, run_id: str, wait: bool = True) -> EvaluationResult:
        """Get evaluation results for a query run."""
        return EvaluationResult(scores={"faithfulness": 0.88, "answer_relevance": 0.92})

    async def list_pipelines(self) -> list[dict]:
        return [{"id": "default"}]

    async def create_pipeline(self, config: dict) -> dict:
        return {"id": "new-pipeline", "config": config}
