import pytest
from pydantic import ValidationError

from backend.models.pipeline import (
    EvaluationConfig,
    GenerationConfig,
    IngestionConfig,
    ModelRoutingConfig,
    PipelineConfig,
    RetrievalConfig,
)


def test_pipeline_config_valid():
    config = PipelineConfig(
        name="Test Pipeline",
        description="A test pipeline",
        ingestion=IngestionConfig(chunk_size_tokens=512, chunk_overlap_tokens=50, chunking_strategy="semantic"),
        retrieval=RetrievalConfig(dense_k=50, top_k_after_rerank=5),
        generation=GenerationConfig(
            model_routing=ModelRoutingConfig(task_type="generation", max_cost_per_call=0.01),
            temperature=0.7
        ),
        evaluation=EvaluationConfig(auto_evaluate=True)
    )
    assert config.name == "Test Pipeline"

def test_pipeline_config_missing_name():
    with pytest.raises(ValidationError):
        PipelineConfig(
            description="No name",
            ingestion=IngestionConfig(),
            retrieval=RetrievalConfig(),
            generation=GenerationConfig(model_routing=ModelRoutingConfig()),
            evaluation=EvaluationConfig()
        )

def test_pipeline_config_invalid_extra_field():
    with pytest.raises(ValidationError):
        IngestionConfig(chunk_size_tokens=512, invalid_extra_field=True) # type: ignore

def test_pipeline_config_invalid_temperature_type():
    with pytest.raises(ValidationError):
        GenerationConfig(model_routing=ModelRoutingConfig(), temperature="very hot") # type: ignore

def test_pipeline_config_invalid_retrieval_extra():
    with pytest.raises(ValidationError):
        RetrievalConfig(dense_k=50, unknown_config=True) # type: ignore
