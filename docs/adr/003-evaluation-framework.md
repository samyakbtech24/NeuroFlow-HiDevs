# ADR 003: Automated Evaluation Using an LLM-as-a-Judge

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The system must continuously evaluate generated responses to measure retrieval and generation quality. Manual evaluation provides high-quality feedback but does not scale as the number of interactions grows.

An automated evaluation framework is therefore required to support continuous monitoring and future model improvement.

The primary evaluation metrics are:

- Faithfulness
- Answer Relevance
- Context Precision
- Context Recall

## Decision

The project will adopt an **LLM-as-a-Judge** evaluation framework.

After each completed response, a background evaluation process scores the generation using the retrieved context and user query. Results are stored in PostgreSQL for reporting, quality monitoring, and future fine-tuning dataset creation.

Human evaluation remains valuable but is reserved for periodic validation rather than every interaction.

## Consequences

### Positive

- Scalable evaluation pipeline
- Consistent scoring methodology
- Enables continuous quality monitoring
- Supports automatic fine-tuning dataset generation
- Reduces manual review effort

### Negative

- Evaluation quality depends on the judging model
- Possible scoring bias
- Additional inference cost
- Scores should not be treated as absolute ground truth

## Mitigation

To improve reliability:

- Periodically compare automated scores with human reviews.
- Track rolling evaluation metrics to detect quality regressions.
- Use multiple evaluation metrics rather than a single score.
- Incorporate user feedback into model performance analysis.

## Rationale

Automated evaluation provides a practical balance between scalability and quality. It enables continuous assessment of the RAG pipeline while retaining human review as a validation mechanism for important or ambiguous cases.