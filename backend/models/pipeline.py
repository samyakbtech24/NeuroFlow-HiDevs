from pydantic import BaseModel, ConfigDict, Field


class IngestionConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    chunking_strategy: str = Field(default="fixed", description="Strategy for chunking documents")
    chunk_size_tokens: int = Field(default=500, description="Target size of chunks in tokens")
    chunk_overlap_tokens: int = Field(default=50, description="Overlap between consecutive chunks")
    extractors_enabled: list[str] = Field(default_factory=list, description="Enabled document extractors (e.g., pdf, docx)")  # noqa: E501

class RetrievalConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    dense_k: int = Field(default=20, description="Number of chunks to retrieve via dense vector search")  # noqa: E501
    sparse_k: int = Field(default=0, description="Number of chunks to retrieve via sparse keyword search")  # noqa: E501
    reranker: str | None = Field(default=None, description="Reranking strategy (e.g., cross-encoder)")  # noqa: E501
    top_k_after_rerank: int = Field(default=5, description="Final number of chunks to send to generator")  # noqa: E501
    query_expansion: bool = Field(default=False, description="Whether to expand queries before retrieval")  # noqa: E501
    metadata_filters_enabled: bool = Field(default=False, description="Whether to apply metadata filtering")  # noqa: E501
    ef_search: int = Field(default=100, description="HNSW ef_search parameter for pgvector tuning")  # noqa: E501
    enable_query_cache: bool = Field(default=True, description="Enable Redis caching for full query results")  # noqa: E501

class ModelRoutingConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    task_type: str = Field(default="rag_generation")
    max_cost_per_call: float = Field(default=0.01)

class GenerationConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    model_routing: ModelRoutingConfig
    max_context_tokens: int = Field(default=4000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    system_prompt_variant: str = Field(default="default")

class EvaluationConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    auto_evaluate: bool = Field(default=False)
    training_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

class PipelineConfig(BaseModel):  # type: ignore
    model_config = ConfigDict(extra='forbid')
    
    name: str = Field(..., description="Unique name for this pipeline")
    description: str | None = Field(default=None, description="Human readable description")
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    evaluation: EvaluationConfig
