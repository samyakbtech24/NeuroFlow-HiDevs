import asyncio
import json
import logging
import os
import sys
import uuid

# Add parent directory to path to allow importing packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import settings

# Override database and redis hosts if running on the host machine (not in docker container)
if not os.path.exists("/.dockerenv"):
    settings.postgres_host = "localhost"
    settings.redis_host = "localhost"

from backend.db.pool import close_pool, get_pool, init_pool
from pipelines.retrieval.retriever import Retriever

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("retrieval-eval")

# Define 50 diverse chunks for seeding
MOCK_CHUNKS = [
    # Topic 1: HNSW Graph Indexing (10 chunks)
    {"id": "c0000001-0000-0000-0000-000000000001", "content": "Hierarchical Navigable Small World (HNSW) graphs are state-of-the-art structures for approximate nearest neighbor search. They build multi-layer graphs where layers have skip list features to speed up vector searches.", "metadata": {"topic": "hnsw", "year": 2022}},
    {"id": "c0000001-0000-0000-0000-000000000002", "content": "An HNSW index search begins at the top layer, finding the nearest neighbors with a greedy search. Once a local minimum is found, the search drops down to the next layer and repeats until the bottom layer is reached.", "metadata": {"topic": "hnsw", "year": 2022}},
    {"id": "c0000001-0000-0000-0000-000000000003", "content": "HNSW index construction parameter M defines the maximum number of outgoing connections in the graph. Higher values of M yield higher search recall but increase indexing memory usage and construction time.", "metadata": {"topic": "hnsw", "year": 2023}},
    {"id": "c0000001-0000-0000-0000-000000000004", "content": "The efConstruction parameter in HNSW controls the size of the dynamic candidate list evaluated during graph creation. Tuning efConstruction increases recall quality at the cost of building times.", "metadata": {"topic": "hnsw", "year": 2023}},
    {"id": "c0000001-0000-0000-0000-000000000005", "content": "HNSW index memory footprints can be large because graph links must be kept in memory alongside raw vector data. Product Quantization (PQ) is often combined to compress vectors inside the graph.", "metadata": {"topic": "hnsw", "year": 2024}},
    {"id": "c0000001-0000-0000-0000-000000000006", "content": "Unlike flat indexing, HNSW does not perform brute force comparison of query vectors against all chunks. It achieves sub-linear search time logarithmic with the dataset size.", "metadata": {"topic": "hnsw", "year": 2024}},
    {"id": "c0000001-0000-0000-0000-000000000007", "content": "The search parameter efSearch determines the search candidate list size during query execution. Setting efSearch higher improves accuracy but increases query latencies.", "metadata": {"topic": "hnsw", "year": 2025}},
    {"id": "c0000001-0000-0000-0000-000000000008", "content": "Graph traversal in HNSW utilizes priority queues to track the closest elements discovered. Visited tables prevent redundant evaluations of graph nodes.", "metadata": {"topic": "hnsw", "year": 2025}},
    {"id": "c0000001-0000-0000-0000-000000000009", "content": "For high-dimensional embeddings, HNSW remains robust against the curse of dimensionality, retaining high recall (>95%) when properly configured.", "metadata": {"topic": "hnsw", "year": 2026}},
    {"id": "c0000001-0000-0000-0000-000000000010", "content": "Adding pgvector HNSW indexing capabilities inside PostgreSQL databases enables fast hybrid SQL and semantic query combinations in production setups.", "metadata": {"topic": "hnsw", "year": 2026}},

    # Topic 2: Climate Change & Global Warming (10 chunks)
    {"id": "c0000002-0000-0000-0000-000000000001", "content": "Climate change refers to long-term shifts in global temperatures and weather patterns. These shifts are primarily driven by greenhouse gas emissions from burning fossil fuels like coal and oil.", "metadata": {"topic": "climate", "year": 2022}},
    {"id": "c0000002-0000-0000-0000-000000000002", "content": "Global warming causes thermal expansion of oceans and melting of ice sheets, leading to rising global sea levels that threaten low-lying coastal cities and ecosystems.", "metadata": {"topic": "climate", "year": 2022}},
    {"id": "c0000002-0000-0000-0000-000000000003", "content": "The Paris Agreement aims to limit global temperature rises to well below 2 degrees Celsius compared to pre-industrial levels, aiming for 1.5 degrees to avoid feedback loops.", "metadata": {"topic": "climate", "year": 2023}},
    {"id": "c0000002-0000-0000-0000-000000000004", "content": "Deforestation releases vast carbon dioxide amounts since trees absorb greenhouse gases. Burning forests double emissions while reducing Earth's carbon capture capacities.", "metadata": {"topic": "climate", "year": 2023}},
    {"id": "c0000002-0000-0000-0000-000000000005", "content": "Renewable energy technologies like solar and wind power provide clean alternatives, lowering emissions from power sectors and electricity grids worldwide.", "metadata": {"topic": "climate", "year": 2024}},
    {"id": "c0000002-0000-0000-0000-000000000006", "content": "Extreme weather events, including intense hurricanes, prolonged heatwaves, and severe droughts, have become more frequent due to rising atmospheric temperatures.", "metadata": {"topic": "climate", "year": 2024}},
    {"id": "c0000002-0000-0000-0000-000000000007", "content": "Carbon tax and cap-and-trade programs place a economic price on emissions, encouraging industries to transition to low-carbon alternatives.", "metadata": {"topic": "climate", "year": 2025}},
    {"id": "c0000002-0000-0000-0000-000000000008", "content": "Methane is a potent greenhouse gas, holding over 80 times the warming power of carbon dioxide in its first 20 years in the atmosphere.", "metadata": {"topic": "climate", "year": 2025}},
    {"id": "c0000002-0000-0000-0000-000000000009", "content": "Climate adaptation involves modifying infrastructure and agricultural practices to withstand extreme floods and changes in regional growing seasons.", "metadata": {"topic": "climate", "year": 2026}},
    {"id": "c0000002-0000-0000-0000-000000000010", "content": "Transitioning to electric vehicles (EVs) helps reduce carbon footprints in transportation sectors, especially when charged via green energy grids.", "metadata": {"topic": "climate", "year": 2026}},

    # Topic 3: Attention Mechanism & Transformers (10 chunks)
    {"id": "c0000003-0000-0000-0000-000000000001", "content": "The Attention Mechanism allows machine learning models to focus on specific parts of an input sequence, mapping relations between far-apart tokens in NLP.", "metadata": {"topic": "attention", "year": 2022}},
    {"id": "c0000003-0000-0000-0000-000000000002", "content": "Self-attention calculations map input sequences to query, key, and value vectors. The dot product of queries and keys determines attention weight distribution.", "metadata": {"topic": "attention", "year": 2022}},
    {"id": "c0000003-0000-0000-0000-000000000003", "content": "Scaled dot-product attention divides dot products by the square root of key dimensions to prevent gradients from exploding during softmax operations.", "metadata": {"topic": "attention", "year": 2023}},
    {"id": "c0000003-0000-0000-0000-000000000004", "content": "Multi-head attention runs self-attention in parallel across different projection spaces, allowing the model to capture multiple relationships simultaneously.", "metadata": {"topic": "attention", "year": 2023}},
    {"id": "c0000003-0000-0000-0000-000000000005", "content": "Transformers drop recurrent neural network (RNN) layers completely, relying entirely on self-attention blocks to capture sequence context.", "metadata": {"topic": "attention", "year": 2024}},
    {"id": "c0000003-0000-0000-0000-000000000006", "content": "Feedforward neural network blocks follow multi-head attention sub-layers, applying non-linear activation functions to token representations.", "metadata": {"topic": "attention", "year": 2024}},
    {"id": "c0000003-0000-0000-0000-000000000007", "content": "Positional encoding adds vector signals to input embeddings to convey token orders since self-attention contains no sequence order biases.", "metadata": {"topic": "attention", "year": 2025}},
    {"id": "c0000003-0000-0000-0000-000000000008", "content": "Layer normalization and residual skip connections surround transformer sub-layers, improving deep neural network gradient backpropagation.", "metadata": {"topic": "attention", "year": 2025}},
    {"id": "c0000003-0000-0000-0000-000000000009", "content": "Masked attention is utilized inside transformer decoders, preventing target tokens from attending to subsequent tokens during auto-regressive generation.", "metadata": {"topic": "attention", "year": 2026}},
    {"id": "c0000003-0000-0000-0000-000000000010", "content": "Cross-attention blocks in sequence-to-sequence models connect decoder layers to encoder output representations, translating information namespaces.", "metadata": {"topic": "attention", "year": 2026}},

    # Topic 4: Retrieval-Augmented Generation RAG (10 chunks)
    {"id": "c0000004-0000-0000-0000-000000000001", "content": "Retrieval-Augmented Generation (RAG) merges LLM generation with database searches, grounding responses in external factual document context.", "metadata": {"topic": "rag", "year": 2022}},
    {"id": "c0000004-0000-0000-0000-000000000002", "content": "RAG reduces AI model hallucinations by providing source documents, allowing generators to quote references instead of recalling facts.", "metadata": {"topic": "rag", "year": 2022}},
    {"id": "c0000004-0000-0000-0000-000000000003", "content": "A standard RAG pipeline includes three core components: document ingestion, vector retrieval, and prompt generation context window assembly.", "metadata": {"topic": "rag", "year": 2023}},
    {"id": "c0000004-0000-0000-0000-000000000004", "content": "Semantic search in RAG pipelines embeds input queries and computes vector cosines to identify the top-k database matching chunks.", "metadata": {"topic": "rag", "year": 2023}},
    {"id": "c0000004-0000-0000-0000-000000000005", "content": "Hybrid search combines sparse keyword indexes and dense vector metrics, merging lists via Reciprocal Rank Fusion (RRF) algorithms.", "metadata": {"topic": "rag", "year": 2024}},
    {"id": "c0000004-0000-0000-0000-000000000006", "content": "Cross-Encoder rerankers refine initial retrieved lists by joint query-content evaluations, filtering out low-quality candidates.", "metadata": {"topic": "rag", "year": 2024}},
    {"id": "c0000004-0000-0000-0000-000000000007", "content": "Context window limits necessitate token budget enforcement, packing document snippets without breaking critical sentences.", "metadata": {"topic": "rag", "year": 2025}},
    {"id": "c0000004-0000-0000-0000-000000000008", "content": "Metadata filtering applies Postgres WHERE clauses to search scopes, scoping lookups to specific years, authors, or topics.", "metadata": {"topic": "rag", "year": 2025}},
    {"id": "c0000004-0000-0000-0000-000000000009", "content": "Prompt engineering for RAG includes system instructions telling models to refuse answers if matching source facts are missing.", "metadata": {"topic": "rag", "year": 2026}},
    {"id": "c0000004-0000-0000-0000-000000000010", "content": "Evaluation metrics like faithfulness and answer relevance measure how closely LLM generations adhere to retrieved chunk facts.", "metadata": {"topic": "rag", "year": 2026}},

    # Topic 5: PostgreSQL Database Optimizations (10 chunks)
    {"id": "c0000005-0000-0000-0000-000000000001", "content": "PostgreSQL database optimization is critical for scaling applications. Creating indices reduces sequential table scan requirements.", "metadata": {"topic": "postgres", "year": 2022}},
    {"id": "c0000005-0000-0000-0000-000000000002", "content": "A GIN (Generalized Inverted Index) is ideal for JSONB and array columns, speeding up inclusion operators like @> containment checks.", "metadata": {"topic": "postgres", "year": 2022}},
    {"id": "c0000005-0000-0000-0000-000000000003", "content": "Full-text search in PostgreSQL leverages to_tsvector to convert contents to lexeme tokens and plainto_tsquery for match matching.", "metadata": {"topic": "postgres", "year": 2023}},
    {"id": "c0000005-0000-0000-0000-000000000004", "content": "Rank functions like ts_rank_cd evaluate keyword densities, factoring in term frequencies and positional distances in matching texts.", "metadata": {"topic": "postgres", "year": 2023}},
    {"id": "c0000005-0000-0000-0000-000000000005", "content": "The EXPLAIN ANALYZE statement outputs query execution plans, outlining index scan operations and row cost estimates.", "metadata": {"topic": "postgres", "year": 2024}},
    {"id": "c0000005-0000-0000-0000-000000000006", "content": "Pgvector enables storing high-dimensional vectors, offering flat indexes (L2 distance) and graph HNSW indices inside tables.", "metadata": {"topic": "postgres", "year": 2024}},
    {"id": "c0000005-0000-0000-0000-000000000007", "content": "Autovacuum daemons clean up dead rows in PostgreSQL tables, preventing index bloat and maintaining statistics accuracy.", "metadata": {"topic": "postgres", "year": 2025}},
    {"id": "c0000005-0000-0000-0000-000000000008", "content": "Connection pooling libraries like asyncpg reduce socket overhead, reusing established backend server connections.", "metadata": {"topic": "postgres", "year": 2025}},
    {"id": "c0000005-0000-0000-0000-000000000009", "content": "Partitioning splits massive tables into smaller child tables, optimizing queries by scanning only relevant child ranges.", "metadata": {"topic": "postgres", "year": 2026}},
    {"id": "c0000005-0000-0000-0000-000000000010", "content": "WAL (Write-Ahead Logging) ensures data integrity, recording transactions to disk logs before updating database pages.", "metadata": {"topic": "postgres", "year": 2026}},
]

# Define 20 test questions mapped to relevant chunk IDs
EVAL_TEST_SET = [
    {"query": "What is Hierarchical Navigable Small World HNSW graphs?", "relevant_chunk_ids": ["c0000001-0000-0000-0000-000000000001"]},
    {"query": "How does HNSW index greedy search traversal work?", "relevant_chunk_ids": ["c0000001-0000-0000-0000-000000000002"]},
    {"query": "Explain construction parameter M in HNSW indexing outgoing connections", "relevant_chunk_ids": ["c0000001-0000-0000-0000-000000000003"]},
    {"query": "How to control candidates size using efConstruction parameter in HNSW?", "relevant_chunk_ids": ["c0000001-0000-0000-0000-000000000004"]},
    {"query": "Tell me about climate change greenhouse gas emissions global warming", "relevant_chunk_ids": ["c0000002-0000-0000-0000-000000000001"]},
    {"query": "How global warming thermal expansion causes sea levels rise?", "relevant_chunk_ids": ["c0000002-0000-0000-0000-000000000002"]},
    {"query": "Explain the Paris Agreement temperature limit of 1.5 degrees", "relevant_chunk_ids": ["c0000002-0000-0000-0000-000000000003"]},
    {"query": "Why deforestation releases carbon dioxide and reduces capture capacity?", "relevant_chunk_ids": ["c0000002-0000-0000-0000-000000000004"]},
    {"query": "Explain self-attention mechanism query key value weights calculation", "relevant_chunk_ids": ["c0000003-0000-0000-0000-000000000002"]},
    {"query": "What is scaled dot-product attention in transformer models?", "relevant_chunk_ids": ["c0000003-0000-0000-0000-000000000003"]},
    {"query": "Explain multi-head attention running in parallel projection spaces", "relevant_chunk_ids": ["c0000003-0000-0000-0000-000000000004"]},
    {"query": "Why transformers drop RNN layers in favor of self-attention?", "relevant_chunk_ids": ["c0000003-0000-0000-0000-000000000005"]},
    {"query": "What is Retrieval-Augmented Generation RAG grounding LLM?", "relevant_chunk_ids": ["c0000004-0000-0000-0000-000000000001"]},
    {"query": "How RAG reduces AI hallucinations providing source context?", "relevant_chunk_ids": ["c0000004-0000-0000-0000-000000000002"]},
    {"query": "What are core components of a standard RAG pipeline?", "relevant_chunk_ids": ["c0000004-0000-0000-0000-000000000003"]},
    {"query": "Explain Reciprocal Rank Fusion RRF hybrid search", "relevant_chunk_ids": ["c0000004-0000-0000-0000-000000000005"]},
    {"query": "What is a GIN Generalized Inverted Index on Postgres JSONB?", "relevant_chunk_ids": ["c0000005-0000-0000-0000-000000000002"]},
    {"query": "How full-text search in PostgreSQL leverages to_tsvector?", "relevant_chunk_ids": ["c0000005-0000-0000-0000-000000000003"]},
    {"query": "How rank function ts_rank_cd evaluates keyword density?", "relevant_chunk_ids": ["c0000005-0000-0000-0000-000000000004"]},
    {"query": "Explain EXPLAIN ANALYZE index scan runtime execution plans", "relevant_chunk_ids": ["c0000005-0000-0000-0000-000000000005"]},
]

async def seed_database():
    """
    Seeds PostgreSQL with a dummy document and 50 mock chunks to enable evaluation.
    """
    pool = get_pool()
    doc_id = uuid.UUID("d0000000-0000-0000-0000-000000000000")
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Insert dummy document
            await conn.execute(
                """
                INSERT INTO documents (id, filename, source_type, content_hash, status, chunk_count, metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET filename = EXCLUDED.filename
                """,
                doc_id,
                "eval_corpus.txt",
                "text",
                "eval_hash_signature",
                "complete",
                50,
                json.dumps({"description": "Evaluation Corpus"})
            )
            
            # 2. Insert 50 chunks
            vector_str = str([0.1] * 1536)  # Mock embedding vector matching dimensions
            for idx, c in enumerate(MOCK_CHUNKS):
                await conn.execute(
                    """
                    INSERT INTO chunks (id, document_id, content, embedding, chunk_index, token_count, metadata, created_at)
                    VALUES ($1, $2, $3, $4::vector, $5, $6, $7::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content
                    """,
                    uuid.UUID(c["id"]),
                    doc_id,
                    c["content"],
                    vector_str,
                    idx,
                    len(c["content"].split()),
                    json.dumps(c["metadata"])
                )
    logger.info("Successfully seeded database with 50 evaluation chunks.")

async def run_evaluation():
    """
    Runs the retrieval pipeline for 20 queries, calculates Hit Rate and MRR,
    and asserts the required quality threshold targets.
    """
    retriever = Retriever()
    
    total_queries = len(EVAL_TEST_SET)
    hits = 0
    mrr_sum = 0.0
    
    print("\nRunning Retrieval Pipeline Evaluation...")
    for idx, test in enumerate(EVAL_TEST_SET, start=1):
        query = test["query"]
        relevant_ids = test["relevant_chunk_ids"]
        
        # Retrieve top 10 chunks
        results = await retriever.retrieve(query, k=10)
        retrieved_ids = [r.chunk_id for r in results]
        
        # Compute metrics
        hit = any(rid in relevant_ids for rid in retrieved_ids)
        rank = None
        for rank_idx, rid in enumerate(retrieved_ids, start=1):
            if rid in relevant_ids:
                rank = rank_idx
                break
                
        if hit:
            hits += 1
            mrr_sum += 1.0 / rank
            
        print(f"Query {idx:02d}: '{query[:50]}...' -> Hit: {hit}, First Rank: {rank}")

    hit_rate = hits / total_queries
    mrr = mrr_sum / total_queries
    
    print("\nFinal Results:")
    print(f"  Hit Rate: {hit_rate:.4f} (Required > 0.75)")
    print(f"  MRR:      {mrr:.4f} (Required > 0.55)")
    
    # Save scores
    results_json = {
        "hit_rate": hit_rate,
        "mrr": mrr
    }
    
    os.makedirs(os.path.dirname(os.path.abspath("evaluation/retrieval_results.json")), exist_ok=True)
    with open("evaluation/retrieval_results.json", "w") as f:
        json.dump(results_json, f, indent=2)
        
    logger.info("Scores written to evaluation/retrieval_results.json")
    
    # Assert quality threshold gates
    assert hit_rate > 0.75, f"Hit Rate of {hit_rate:.2f} failed to meet threshold of 0.75"
    assert mrr > 0.55, f"MRR of {mrr:.2f} failed to meet threshold of 0.55"
    print("\nRetrieval Pipeline successfully passed all quality threshold checks!")

async def main():
    await init_pool(settings.database_url)
    try:
        await seed_database()
        await run_evaluation()
    finally:
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
