
from pydantic import BaseModel


class Document(BaseModel):
    id: str
    status: str

class QueryResult(BaseModel):
    answer: str
    sources: list[dict]

class EvaluationResult(BaseModel):
    scores: dict[str, float]
