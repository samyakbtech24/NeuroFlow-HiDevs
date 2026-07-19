import asyncio
import logging
import re

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria

logger = logging.getLogger("metric-precision")

async def evaluate_context_precision(query: str, chunks: list[str], answer: str) -> float:
    """
    Evaluates context precision: were the retrieved chunks actually relevant and useful,
    and were the most useful ones ranked higher?
    Returns a score between 0.0 and 1.0.
    """
    if not chunks:
        return 1.0  # Default to 1.0 if no chunks were retrieved
        
    client = NeuroFlowClient()
    useful_flags = []

    # 1. Heuristic utility estimator for Mock mode (checks word overlap against generated answer)
    if client.openai_key == "mock":
        stop_words = {"what", "is", "a", "the", "in", "on", "to", "of", "and", "for", "with", "how"}
        answer_words = set(w.lower() for w in re.findall(r'\w+', answer) if w.lower() not in stop_words)
        
        for chunk in chunks:
            chunk_words = set(w.lower() for w in re.findall(r'\w+', chunk) if w.lower() not in stop_words)
            overlap = chunk_words.intersection(answer_words)
            # Mark useful if there are at least 3 distinct keywords overlapping
            useful_flags.append(1.0 if len(overlap) >= 3 else 0.0)
            
    # 2. Real LLM-as-Judge Mode
    else:
        async def check_utility(chunk: str) -> float:
            prompt = (
                f"Query: {query}\n"
                f"Generated Answer: {answer}\n"
                f"Retrieved Passage: {chunk}\n\n"
                f"Was this retrieved passage useful in generating the answer? Answer exactly yes or no."
            )
            try:
                res = await client.chat(
                    [ChatMessage(role="user", content=prompt)],
                    RoutingCriteria(task_type="evaluation")
                )
                decision = res.content.strip().lower()
                if "yes" in decision:
                    return 1.0
            except Exception as e:
                logger.warning(f"Utility check failed for chunk: {e}")
            return 0.0

        tasks = [check_utility(c) for c in chunks]
        useful_flags = await asyncio.gather(*tasks)

    # 3. Calculate rank-weighted context precision score
    # Score = sum(useful[i] * (1/i) for i in ranks) / sum(1/i for i in ranks)
    # where i is 1-based index (rank)
    numerator = sum(flag * (1.0 / (idx + 1)) for idx, flag in enumerate(useful_flags))
    denominator = sum(1.0 / (idx + 1) for idx in range(len(chunks)))
    
    if denominator == 0:
        return 0.0
        
    score = numerator / denominator
    return round(score, 4)
