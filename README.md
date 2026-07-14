# ArXiv Research Assistant

A production-grade Retrieval-Augmented Generation (RAG) system for searching, retrieving, and chatting with arXiv research papers using hybrid retrieval and modern LLMs.

---

# Project Goal

Build a production-grade RAG system for arXiv papers featuring:

- Hybrid retrieval
- Intelligent reranking
- Accurate citations
- Evaluation pipeline
- Production-ready deployment
- Scalable document ingestion
- Modern backend architecture

---
# Architecture

```text
                          User
                            │
                            ▼
                    Next.js Frontend
                            │
                            ▼
                     FastAPI Backend
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
          ▼                                   ▼
   Retrieval Pipeline                 Background Jobs
          │                                   │
          ▼                                   ▼
      Hybrid Search                  Celery + Redis
          │                                   │
     ┌────┴────┐                              │
     ▼         ▼                              ▼
   BM25   Vector Search              PDF Processing
          │                                   │
          └──────────────┬────────────────────┘
                         ▼
                     Reranker
                         │
                         ▼
                  Context Builder
                         │
                         ▼
                      GPT-4.1
                         │
                         ▼
                      Response

                 PostgreSQL + pgvector
```

---

# Tech Stack

### Frontend
- Next.js 15
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query (React Query)
- Zustand
- Framer Motion

### Backend
- FastAPI
- Python 3.12
- SQLAlchemy
- Pydantic
- Celery
- Redis

### AI
**Embeddings**
- BAAI `bge-large-en-v1.5`

**Reranker**
- BAAI `bge-reranker-large`

**LLM**
- GPT-4.1

### Database
- PostgreSQL
- pgvector

### Search
- BM25
- Dense Vector Search
- Reciprocal Rank Fusion (RRF)

### Evaluation
- Ragas
- DeepEval

### DevOps & Deployment
- Docker
- Docker Compose
- GitHub Actions
- OpenTelemetry
- Prometheus
- Grafana
- Render
-----------------------------------------------

Document Ingestion Pipeline

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
 Embedding Generation
     |
     v
 PostgreSQL + pgvector
```

---

# Folder Structure

```text
arxiv-rag-assistant/
│
├── app/
│   ├── api/
│   ├── core/
│   ├── database/
│   ├── ingestion/
│   ├── services/
│   ├── models/
│   └── utils/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── scripts/
├── tests/
├── docker/
│
├── requirements.txt
├── docker-compose.yml
├── .env
├── README.md
└── main.py
```

---

# Future Roadmap

- Hybrid search (Dense + BM25)
- Reranking pipeline
- Streaming chat responses
- Conversation memory
- Citation support
- Authentication
- Background ingestion workers
- Evaluation framework
- Monitoring and observability
- Paper comparison
- Citation graph visualization
- Research recommendations
- Bookmarking
- Trend dashboard
