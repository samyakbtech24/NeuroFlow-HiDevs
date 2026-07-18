from pydantic import BaseModel
from typing import List, Dict

class Document(BaseModel):
    id: str
    status: str

class QueryResult(BaseModel):
    answer: str
    sources: List[Dict]

class EvaluationResult(BaseModel):
    scores: Dict[str, float]
