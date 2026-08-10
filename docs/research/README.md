# Research

Deep-dive research that extends the design docs. Read these when implementing deferred features
(ingestion, AI orchestration, or richer student/teacher UI).

| Document | Summary | Related design |
| --- | --- | --- |
| [ai-rag-integration.md](./ai-rag-integration.md) | Production RAG topology: async ingestion, hybrid retrieval, RBAC filters, RAGAS evaluation | [04 material lifecycle](../design/04-material-lifecycle-and-ai-artifacts.md) |
| [ui-platform-research.md](./ui-platform-research.md) | UI paradigm research: split-screen layouts, typography, assessment UX patterns | [01 student learning experience](../design/01-student-learning-experience.md), [assets](../assets/) mockups |

## When to read each doc

- **ai-rag-integration.md** — Before designing document ingestion, vector indexing, or the grounded
  AI assistant. Covers PDF parsing, chunking, embedding storage, retrieval filters tied to JWT
  claims, and evaluation with RAGAS.
- **ui-platform-research.md** — Before major student or teacher UI work. Compares documentation
  engines, spatial layouts (split-screen, three-column, course-player), and assessment interaction
  patterns. Informs [assets/](../assets/) HTML mockups.

Return to the [documentation hub](../README.md) for implementation status and reading paths.
