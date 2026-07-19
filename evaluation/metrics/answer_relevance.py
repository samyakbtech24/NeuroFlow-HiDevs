import json
import logging
import math
import re

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria

logger = logging.getLogger("metric-relevance")

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """
    Computes the cosine similarity between two float vectors.
    """
    dot_product = sum(a * b for a, b in zip(v1, v2))
    magnitude_v1 = math.sqrt(sum(a * a for a in v1))
    magnitude_v2 = math.sqrt(sum(a * a for a in v2))
    if magnitude_v1 == 0 or magnitude_v2 == 0:
        return 0.0
    return dot_product / (magnitude_v1 * magnitude_v2)

async def evaluate_answer_relevance(query: str, answer: str) -> float:
    """
    Evaluates answer relevance: does the answer address the question asked?
    Returns a score between 0.0 and 1.0.
    """
    if not answer.strip() or not query.strip():
        return 0.0

    client = NeuroFlowClient()

    # 1. Heuristic overlap simulator for Mock mode (ensures realistic varying relevance scores)
    if client.openai_key == "mock":
        stop_words = {"what", "is", "a", "the", "in", "on", "to", "of", "and", "for", "with", "how"}
        query_words = set(w.lower() for w in re.findall(r'\w+', query) if w.lower() not in stop_words)
        if not query_words:
            return 1.0
            
        answer_words = set(w.lower() for w in re.findall(r'\w+', answer))
        matches = query_words.intersection(answer_words)
        
        # Calculate ratio of query words appearing in the answer
        ratio = len(matches) / len(query_words)
        
        # Scale to a realistic cosine similarity range (typically between 0.5 and 1.0)
        score = 0.5 + 0.5 * ratio
        return round(score, 4)

    # 2. Real LLM-as-Judge Mode
    # Step 2a: Generate questions that the answer could respond to
    prompt = (
        f"Generate exactly 3 alternative questions that the following text could be a response to. "
        f"Return ONLY a JSON list of strings. Do not include markdown code formatting.\n"
        f"Text: {answer}"
    )
    
    try:
        res = await client.chat(
            [ChatMessage(role="user", content=prompt)],
            RoutingCriteria(task_type="evaluation")
        )
        match = re.search(r'\[.*\]', res.content.replace('\n', ' '))
        generated_questions = json.loads(match.group(0)) if match else []
    except Exception as e:
        logger.error(f"Failed to generate questions for answer relevance: {e}")
        return 0.5

    if not generated_questions:
        return 0.0

    # Step 2b: Embed the original query and all generated questions
    try:
        all_texts = [query] + generated_questions
        embeddings = await client.embed(all_texts)
        
        query_embedding = embeddings[0]
        question_embeddings = embeddings[1:]
    except Exception as e:
        logger.error(f"Failed to generate embeddings for answer relevance: {e}")
        return 0.5

    # Step 2c: Calculate mean cosine similarity
    similarities = [cosine_similarity(query_embedding, q_emb) for q_emb in question_embeddings]
    mean_score = sum(similarities) / len(similarities)
    
    return round(mean_score, 4)
