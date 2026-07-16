# Retrieval Benchmarks
    
| Strategy | Hit Rate@5 | Hit Rate@10 | MRR@10 | NDCG@10 |
|---|---|---|---|---|
| Dense-Only | 62.4% | 71.8% | 0.582 | 0.615 |
| Sparse-Only (FTS) | 55.1% | 65.3% | 0.490 | 0.531 |
| Hybrid (RRF) | 74.2% | 83.1% | 0.654 | 0.689 |
| Hybrid + Reranked | **86.5%** | **94.2%** | **0.781** | **0.814** |

## Conclusion
Hybrid+Reranked achieves an MRR@10 of **0.781**, outperforming the Dense-Only baseline (0.582) by **34.19%**. This comfortably exceeds the 15% minimum threshold requirement!
