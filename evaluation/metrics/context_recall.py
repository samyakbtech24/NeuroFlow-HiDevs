import asyncio
import logging
import re

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria

logger = logging.getLogger("metric-recall")

async def evaluate_context_recall(query: str, chunks: list[str], answer: str) -> float:
    """
    Evaluates context recall: were the relevant sources retrieved to cover the generated answer?
    Returns a score between 0.0 and 1.0.
    """
    if not answer.strip():
        return 1.0
        
    if not chunks:
        return 0.0

    context_text = "\n".join(chunks)
    
    # Break answer into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', answer) if s.strip()]
    if not sentences:
        return 1.0

    client = NeuroFlowClient()
    attributions = []

    # 1. Heuristic attribution check for Mock mode (Jaccard overlap against combined context)
    if client.openai_key == "mock":
        stop_words = {"what", "is", "a", "the", "in", "on", "to", "of", "and", "for", "with", "how"}
        context_lower = context_text.lower()
        
        for sentence in sentences:
            words = [w.lower() for w in re.findall(r'\w+', sentence) if w.lower() not in stop_words]
            if not words:
                attributions.append(1.0)
                continue
                
            matches = sum(1 for w in words if w in context_lower)
            ratio = matches / len(words)
            
            # Sentence is considered recalled if at least 55% of its key terms exist in retrieved context
            attributions.append(1.0 if ratio >= 0.55 else 0.0)

    # 2. Real LLM-as-Judge Mode
    else:
        async def check_attribution(sentence: str) -> float:
            prompt = (
                f"Context: {context_text}\n\n"
                f"Sentence: {sentence}\n\n"
                f"Can this sentence be attributed to the provided context? Answer exactly yes or no."
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
                logger.warning(f"Attribution check failed for sentence: {e}")
            return 0.0

        tasks = [check_attribution(s) for s in sentences]
        attributions = await asyncio.gather(*tasks)

    # 3. Compute score: attributable_sentences / total_sentences
    score = sum(attributions) / len(sentences)
    return round(score, 4)
