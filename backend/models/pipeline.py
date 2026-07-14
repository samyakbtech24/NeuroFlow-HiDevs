from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class IngestionConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    chunking_strategy: str = Field(default="fixed", description="Strategy for chunking documents")
    chunk_size_tokens: int = Field(default=500, description="Target size of chunks in tokens")
    chunk_overlap_tokens: int = Field(default=50, description="Overlap between consecutive chunks")
    extractors_enabled: List[str] = Field(default_factory=list, description="Enabled document extractors (e.g., pdf, docx)")

class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    dense_k: int = Field(default=20, description="Number of chunks to retrieve via dense vector search")
    sparse_k: int = Field(default=0, description="Number of chunks to retrieve via sparse keyword search")
    reranker: Optional[str] = Field(default=None, description="Reranking strategy (e.g., cross-encoder)")
    top_k_after_rerank: int = Field(default=5, description="Final number of chunks to send to generator")
    query_expansion: bool = Field(default=False, description="Whether to expand queries before retrieval")
    metadata_filters_enabled: bool = Field(default=False, description="Whether to apply metadata filtering")

class ModelRoutingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    task_type: str = Field(default="rag_generation")
    max_cost_per_call: float = Field(default=0.01)

class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    model_routing: ModelRoutingConfig
    max_context_tokens: int = Field(default=4000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    system_prompt_variant: str = Field(default="default")

class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    auto_evaluate: bool = Field(default=False)
    training_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    name: str = Field(..., description="Unique name for this pipeline")
    description: Optional[str] = Field(default=None, description="Human readable description")
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    evaluation: EvaluationConfig
