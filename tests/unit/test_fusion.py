from pipelines.retrieval.fusion import reciprocal_rank_fusion
from pipelines.retrieval.retriever import RetrievalResult


def test_rrf_empty_lists():
    results = reciprocal_rank_fusion([])
    assert len(results) == 0

def test_rrf_single_list():
    res1 = RetrievalResult(chunk_id="c1", document_id="d1", content="t", score=0.9, metadata={})
    lists = [[res1]]
    results = reciprocal_rank_fusion(lists)
    assert len(results) == 1
    assert results[0].chunk_id == "c1"

def test_rrf_multiple_lists_scoring():
    r1 = RetrievalResult(chunk_id="c1", document_id="d1", content="t", score=0.9, metadata={})
    r2 = RetrievalResult(chunk_id="c2", document_id="d1", content="t", score=0.8, metadata={})
    lists = [[r1, r2], [r2, r1]]
    results = reciprocal_rank_fusion(lists)
    assert len(results) == 2
    # RRF score = 1/(60+1) + 1/(60+2) = 1/61 + 1/62 for both, should be same
    assert abs(results[0].score - results[1].score) < 0.001

def test_rrf_k_parameter():
    r1 = RetrievalResult(chunk_id="c1", document_id="d1", content="t", score=0.9, metadata={})
    lists = [[r1]]
    results = reciprocal_rank_fusion(lists, k=10)
    assert results[0].score == 1 / (10 + 1)

def test_rrf_metadata_preservation():
    r1 = RetrievalResult(chunk_id="c1", document_id="d1", content="t", score=0.9, metadata={"key": "val"})
    lists = [[r1]]
    results = reciprocal_rank_fusion(lists)
    assert results[0].metadata["key"] == "val"
