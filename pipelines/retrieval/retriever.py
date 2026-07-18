import asyncio
import json
import logging
import time
import contextlib
from dataclasses import dataclass
from typing import List, Dict, Optional
import uuid

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.fusion import reciprocal_rank_fusion
from pipelines.retrieval.reranker import CrossEncoderReranker
from backend.monitoring.metrics import retrieval_latency

logger = logging.getLogger("retriever")

try:
    from opentelemetry import trace
    tracer = trace.get_tracer("neuroflow-retriever")
except ImportError:
    tracer = None

@dataclass
class RetrievalResult:
    """
    Represents a retrieved chunk with its content and relevance score.
    """
    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: Dict  # type: ignore

class Retriever:
    """
    Coordinates the hybrid retrieval pipeline.
    Executes dense, sparse, and metadata searches in parallel, fuses them via RRF,
    and refines the ranking using a Cross-Encoder reranker.
    """
    
    def __init__(self):  # type: ignore
        self.processor = QueryProcessor()
        self.reranker = CrossEncoderReranker()

    async def _dense_retrieval(self, query: str, expansions: List[str], k: int) -> List[RetrievalResult]:
        ctx = tracer.start_as_current_span("retrieval.dense") if tracer else contextlib.nullcontext()
        with ctx:
            client = NeuroFlowClient()
            pool = get_pool()
            
            queries_to_embed = [query] + expansions
            
            try:
                embeddings = await client.embed(queries_to_embed)
            except Exception as e:
                logger.error(f"Failed to generate embeddings for dense search: {e}")
                return []

            tasks = []
            async def run_vector_search(vector: List[float]):  # type: ignore
                vector_str = str(vector)
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, document_id, content, metadata, (embedding <=> $1::vector) as distance
                        FROM chunks
                        ORDER BY distance ASC
                        LIMIT $2
                        """,
                        vector_str,
                        k
                    )
                    return rows

            for emb in embeddings:
                tasks.append(run_vector_search(emb))
                
            results_lists = await asyncio.gather(*tasks)
            
            merged_chunks = {}  # type: ignore
            for rows in results_lists:
                for row in rows:
                    chunk_id = str(row["id"])
                    distance = float(row["distance"])
                    score = 1.0 - distance
                    
                    if chunk_id not in merged_chunks or score > merged_chunks[chunk_id]["score"]:
                        merged_chunks[chunk_id] = {
                            "chunk_id": chunk_id,
                            "document_id": str(row["document_id"]),
                            "content": row["content"],
                            "score": score,
                            "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                        }
                        
            sorted_results = sorted(merged_chunks.values(), key=lambda x: x["score"], reverse=True)[:k]
            return [RetrievalResult(**r) for r in sorted_results]

    async def _sparse_retrieval(self, query: str, k: int) -> List[RetrievalResult]:
        ctx = tracer.start_as_current_span("retrieval.sparse") if tracer else contextlib.nullcontext()
        with ctx:
            import re
            cleaned = re.sub(r'[^\w\s]', ' ', query)
            words = [w for w in cleaned.split() if len(w) > 1]
            tsquery_str = " | ".join(words) if words else query
            
            pool = get_pool()
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, document_id, content, metadata, 
                               ts_rank_cd(to_tsvector('english', content), to_tsquery('english', $1)) as rank
                        FROM chunks
                        WHERE to_tsvector('english', content) @@ to_tsquery('english', $1)
                        ORDER BY rank DESC
                        LIMIT $2
                        """,
                        tsquery_str,
                        k
                    )
                    
                    results = []
                    for row in rows:
                        results.append(RetrievalResult(
                            chunk_id=str(row["id"]),
                            document_id=str(row["document_id"]),
                            content=row["content"],
                            score=float(row["rank"]),
                            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                        ))
                    return results
            except Exception as e:
                logger.error(f"FTS sparse retrieval failed: {e}")
                return []

    async def _metadata_retrieval(self, filters: Dict, query: str, k: int) -> List[RetrievalResult]:  # type: ignore
        ctx = tracer.start_as_current_span("retrieval.metadata") if tracer else contextlib.nullcontext()
        with ctx:
            if not filters:
                return []
                
            pool = get_pool()
            client = NeuroFlowClient()
            
            try:
                embeddings = await client.embed([query])
                vector_str = str(embeddings[0]) if embeddings else str([0.0] * 1536)
                
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, document_id, content, metadata, (embedding <=> $2::vector) as distance
                        FROM chunks
                        WHERE metadata @> $1::jsonb
                        ORDER BY distance ASC
                        LIMIT $3
                        """,
                        json.dumps(filters),
                        vector_str,
                        k
                    )
                    
                    results = []
                    for row in rows:
                        distance = float(row["distance"])
                        results.append(RetrievalResult(
                            chunk_id=str(row["id"]),
                            document_id=str(row["document_id"]),
                            content=row["content"],
                            score=1.0 - distance,
                            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                        ))
                    return results
            except Exception as e:
                logger.error(f"Metadata filtered retrieval failed: {e}")
                return []

    async def retrieve(self, query: str, k: int = 20) -> List[RetrievalResult]:
        start_time = time.time()
        parent_ctx = tracer.start_as_current_span("retrieval.pipeline") if tracer else contextlib.nullcontext()
        with parent_ctx as parent_span:
            expansions = await self.processor.expand_query(query)
            filters = await self.processor.extract_filters(query)
            
            dense_task = self._dense_retrieval(query, expansions, k=k)
            sparse_task = self._sparse_retrieval(query, k=k)
            metadata_task = self._metadata_retrieval(filters, query, k=k)
            
            dense_res, sparse_res, meta_res = await asyncio.gather(
                dense_task, sparse_task, metadata_task
            )
            
            fusion_ctx = tracer.start_as_current_span("retrieval.fusion") if tracer else contextlib.nullcontext()
            with fusion_ctx:
                fused_results = reciprocal_rank_fusion([dense_res, sparse_res, meta_res], k=60)
            
            rerank_ctx = tracer.start_as_current_span("retrieval.rerank") if tracer else contextlib.nullcontext()
            with rerank_ctx:
                top_fused = fused_results[:40]
                reranked_results = await self.reranker.rerank(query, top_fused)
            
            final_results = reranked_results[:k]
            
            duration = time.time() - start_time
            retrieval_latency.labels(strategy="hybrid").observe(duration)
            
            if parent_span and hasattr(parent_span, "set_attribute"):
                parent_span.set_attribute("chunk_count", len(final_results))
                parent_span.set_attribute("latency", duration)
            
            return final_results
