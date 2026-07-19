import json
import logging
import re

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria

logger = logging.getLogger("query-processor")

class QueryProcessor:
    """
    Pre-processes raw user queries before running retrieval.
    Performs query expansion, metadata filter extraction, and query type classification.
    """
    
    async def expand_query(self, query: str) -> list[str]:
        """
        Generates 2-3 alternative phrasings of the query to improve dense retrieval recall.
        """
        client = NeuroFlowClient()
        
        # Local programmatic variations if in Mock mode
        if client.openai_key == "mock":
            return [
                f"{query} explanation",
                f"{query} mechanism",
                f"{query} overview"
            ]
            
        # Call LLM for real expansions
        prompt = (
            f"Generate exactly 2 alternative search phrasings for the following query. "
            f"Return only a JSON array of strings. Do not include markdown code blocks. "
            f"Query: {query}"
        )
        try:
            result = await client.chat(
                [ChatMessage(role="user", content=prompt)],
                RoutingCriteria(task_type="classification")
            )
            # Find and parse JSON array
            match = re.search(r'\[.*\]', result.content.replace('\n', ' '))
            if match:
                return json.loads(match.group(0))  # type: ignore
        except Exception as e:
            logger.warning(f"LLM query expansion failed: {e}. Falling back to default variations.")
            
        return [f"{query} details", f"{query} concepts"]

    async def extract_filters(self, query: str) -> dict:  # type: ignore
        """
        Detects implicit year and topic filters in the query text.
        Returns a dictionary of filters (e.g. {"year": 2023, "topic": "climate"}).
        """
        filters = {}
        
        # 1. Regex check for four-digit year (e.g. 2023)
        year_match = re.search(r'\b(19|20)\d{2}\b', query)
        if year_match:
            filters["year"] = int(year_match.group(0))
            
        # 2. Regex check for common topics
        topics = ["climate", "transformer", "attention", "rag", "database", "postgres"]
        for t in topics:
            if t in query.lower():
                filters["topic"] = t  # type: ignore
                break
                
        client = NeuroFlowClient()
        if client.openai_key == "mock":
            return filters
            
        # 3. Call LLM for real filter extraction
        prompt = (
            f"Extract year (integer) and topic (string) filters from the query. "
            f"Return only a JSON object like: {{\"year\": 2023, \"topic\": \"climate\"}}. "
            f"If none are present, return an empty object {{}}. "
            f"Query: {query}"
        )
        try:
            result = await client.chat(
                [ChatMessage(role="user", content=prompt)],
                RoutingCriteria(task_type="classification")
            )
            match = re.search(r'\{.*\}', result.content.replace('\n', ' '))
            if match:
                llm_filters = json.loads(match.group(0))
                # Merge extracted filters
                filters.update(llm_filters)
        except Exception as e:
            logger.warning(f"LLM filter extraction failed: {e}")
            
        return filters

    async def classify_query(self, query: str) -> str:
        """
        Classifies the query as one of: factual, analytical, comparative, or procedural.
        """
        # 1. Local heuristic classifications
        query_lower = query.lower()
        if any(w in query_lower for w in ["how to", "steps", "guide", "process", "install"]):
            heuristic_class = "procedural"
        elif any(w in query_lower for w in ["difference", "versus", "vs", "compare", "comparison"]):
            heuristic_class = "comparative"
        elif any(w in query_lower for w in ["why", "explain", "reason", "cause"]):
            heuristic_class = "analytical"
        else:
            heuristic_class = "factual"
            
        client = NeuroFlowClient()
        if client.openai_key == "mock":
            return heuristic_class
            
        # 2. Call LLM for real query classification
        prompt = (
            f"Classify the query into exactly one of these categories: factual, analytical, comparative, procedural. "
            f"Return only the chosen word in lowercase. "
            f"Query: {query}"
        )
        try:
            result = await client.chat(
                [ChatMessage(role="user", content=prompt)],
                RoutingCriteria(task_type="classification")
            )
            val = result.content.strip().lower()
            if val in ["factual", "analytical", "comparative", "procedural"]:
                return val
        except Exception as e:
            logger.warning(f"LLM query classification failed: {e}. Using heuristic category.")
            
        return heuristic_class
