import asyncio
import logging
import re
from typing import List

from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria

logger = logging.getLogger("reranker")

class CrossEncoderReranker:
    """
    Reranks the top Reciprocal Rank Fusion (RRF) results using a Cross-Encoder approach.
    Evaluates the joint relevance of the query and each chunk.
    """
    
    async def _score_pair(self, query: str, chunk: "RetrievalResult") -> float:
        """
        Calculates a relevance score from 0.0 to 10.0 for a single (query, chunk) pair.
        - In Mock mode: computes a keyword overlap ratio (excluding stop words) as a heuristic.
        - In Real mode: queries the LLM to score the passage relevance.
        """
        client = NeuroFlowClient()
        
        # 1. Heuristic Keyword Overlap for Mock mode (100% free, ensures high Hit Rate/MRR)
        if client.openai_key == "mock":
            stop_words = {
                "what", "is", "a", "the", "in", "on", "to", "of", "and", "for", "with", 
                "how", "does", "do", "about", "from", "show", "me", "documents", "document"
            }
            # Clean and tokenize query
            query_words = [
                w.lower() for w in re.findall(r'\w+', query) 
                if w.lower() not in stop_words
            ]
            if not query_words:
                return 0.0
                
            content_lower = chunk.content.lower()
            matches = sum(1 for w in query_words if w in content_lower)
            
            # Map ratio to 0-10 scale
            return (matches / len(query_words)) * 10.0
            
        # 2. Real LLM scoring call
        prompt = (
            f"Rate the relevance of this passage to the query on a scale of 0-10.\n"
            f"Query: {query}\n"
            f"Passage: {chunk.content}\n"
            f"Return only the number representing the score."
        )
        try:
            result = await client.chat(
                [ChatMessage(role="user", content=prompt)],
                RoutingCriteria(task_type="classification")
            )
            # Find the first floating-point or integer digit in the response
            match = re.search(r'\b\d+(\.\d+)?\b', result.content)
            if match:
                return float(match.group(0))
        except Exception as e:
            logger.warning(f"Reranker LLM scoring failed for chunk {chunk.chunk_id}: {e}")
            
        return 0.0

    async def rerank(self, query: str, chunks: List["RetrievalResult"]) -> List["RetrievalResult"]:
        """
        Scores all candidate chunks in parallel and sorts them descending by score.
        """
        if not chunks:
            return []
            
        # Score all query-chunk pairs in parallel using asyncio.gather
        tasks = [self._score_pair(query, chunk) for chunk in chunks]
        scores = await asyncio.gather(*tasks)
        
        # Update chunks with normalized scores [0.0, 1.0]
        reranked_chunks = []
        for chunk, score in zip(chunks, scores):
            chunk.score = score / 10.0  # Normalize to 0.0 - 1.0 range
            reranked_chunks.append(chunk)
            
        # Sort chunks descending by relevance score
        reranked_chunks.sort(key=lambda x: x.score, reverse=True)
        return reranked_chunks
