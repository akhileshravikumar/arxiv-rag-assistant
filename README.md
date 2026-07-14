# ArXiv Research Assistant

A production-grade Retrieval-Augmented Generation (RAG) system for searching, retrieving, and chatting with arXiv research papers using hybrid retrieval, reranking, and modern LLMs.

---

# Project Goal

Build a production-grade RAG system for arXiv papers featuring:

- Hybrid retrieval (Dense + BM25)
- Intelligent reranking
- Accurate citations
- Evaluation pipeline
- Production-ready deployment
- Scalable document ingestion
- Modern full-stack architecture

---

# Tech Stack

### Frontend
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend
- FastAPI
- SQLAlchemy
- Pydantic

### AI & Retrieval
- bge-large-en-v1.5 (Embeddings)
- bge-reranker-large
- GPT-4.1
- BM25
- pgvector

### Database & Infrastructure
- PostgreSQL
- pgvector
- Redis
- Celery
- Docker
- GitHub Actions
- OpenTelemetry
- Grafana

---

# Architecture

```
                +----------------------+
                |      Next.js UI      |
                +----------+-----------+
                           |
                           |
                     REST / Streaming
                           |
                           v
                +----------------------+
                |       FastAPI        |
                +----------+-----------+
                           |
          +----------------+----------------+
          |                                 |
          |                                 |
          v                                 v
  Hybrid Retrieval                  Conversation
(BM25 + pgvector)                     Memory
          |
          v
      Reranker
          |
          v
    Context Builder
          |
          v
         LLM
          |
          v
      Final Response

-----------------------------------------------

Background Pipeline

arXiv API
     |
     v
 PDF Download
     |
     v
 PDF Parsing
     |
     v
 Metadata Extraction
     |
     v
 Chunking
     |
     v
 Embeddings
     |
     v
PostgreSQL + pgvector

Executed asynchronously using Celery + Redis.
```

---

# Folder Structure

```
.
├── backend/
├── frontend/
├── worker/
├── docs/
├── tests/
├── evaluation/
├── benchmark_dataset/
└── .github/
    └── workflows/
```

---

# Future Roadmap

- Paper comparison
- Citation graph visualization
- Research paper recommendations
- Bookmarks and saved collections
- Research trend dashboard
- MCP server integration
