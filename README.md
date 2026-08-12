# ArXiv Research Assistant

A retrieval-augmented research assistant. Start a session, load up to five
papers — from an arXiv search or your own PDF uploads — then ask questions and
get answers with inline citations back to the source passages.

Sessions are ephemeral. Papers, chunks and embeddings are deleted when a session
expires, so the deployment holds no long-lived user data.

---

## How it works

```
1. Start a session          POST /sessions            → session_id
2. Add papers (max 5)
   a. Search arXiv          GET  /sessions/{id}/arxiv/search?q=...
      Preview 5 results, pick the ones you want.
      Ingest                POST /sessions/{id}/ingest/arxiv
   b. Or upload PDFs        POST /sessions/{id}/ingest/upload
   Both return a job_id     GET  /jobs/{job_id}       → live progress
3. Ask questions            POST /sessions/{id}/chat  → answer + sources
4. Export references        GET  /sessions/{id}/papers/bibtex
5. Finish                   DELETE /sessions/{id}     (or let it expire)
```

---

## Architecture

```text
                          User
                            │
                            ▼
                    Next.js frontend
                            │
                            ▼
                     FastAPI backend
                            │
          ┌─────────────────┴─────────────────┐
          ▼                                   ▼
   Retrieval pipeline                Ingestion jobs
          │                          (BackgroundTasks)
          ▼                                   │
      Hybrid search                           ▼
          │                          arXiv API / PDF upload
     ┌────┴────┐                              │
     ▼         ▼                              ▼
   BM25   Vector search                 PDF extraction
  (per-session,    │                          │
   in-memory)      │                       Chunking
          └────────┴──────────────┬───────────┘
                                  ▼
                            Reranker (API)
                                  ▼
                           Context builder
                                  ▼
                                 LLM
                                  ▼
                        Answer with citations

                       PostgreSQL + pgvector
                        Redis (cache, jobs)
```

Retrieval is scoped to one session at every stage. Dense search filters on
`papers.session_id`; the BM25 index is built per session on demand and cached
least-recently-used, so it holds no cross-session state.

---

## Tech stack

**Frontend** — Next.js 15, React, TypeScript, Tailwind CSS, TanStack Query, Zustand

**Backend** — FastAPI, Python 3.12, SQLAlchemy, Pydantic

**Retrieval** — BM25 (`rank-bm25`), dense vector search (pgvector), Reciprocal
Rank Fusion, cross-encoder reranking

**AI** — OpenAI `text-embedding-3-small` at 384 dimensions for embeddings,
Cohere `rerank-v3.5` for reranking (optional), OpenAI for answer generation

**Data** — PostgreSQL with pgvector, Redis for the answer cache and job state

**Deployment** — Docker, Docker Compose, GitHub Actions, Render, Neon, Upstash, Vercel

No model weights are loaded in-process. Embeddings and reranking run over hosted
APIs, which keeps the container small and startup fast enough for a free-tier
instance.

---

## Running locally

```bash
cp .env.example .env          # add your OPENAI_API_KEY
docker compose up --build
```

Then open http://localhost:8000/docs and drive the full flow from Swagger UI:
create a session, search arXiv, ingest, poll the job, ask a question.

Run the tests:

```bash
python -m pytest
```

---

## Configuration

Every setting has a default; see `.env.example` for the full list. The ones that
matter most:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL with the `vector` extension enabled |
| `REDIS_URL` | Answer cache, query-embedding cache, job state, rate limits |
| `OPENAI_API_KEY` | Required. Used for embeddings and answer generation |
| `OPENAI_MODEL` | Generation model. `gpt-4.1-mini` is a good default |
| `COHERE_API_KEY` | Optional. Without it, reranking falls back to fusion order |
| `SESSION_TTL_SECONDS` | How long an idle session survives (default 2 hours) |
| `MAX_PAPERS_PER_SESSION` | Default 5 |
| `FRONTEND_ORIGINS` | Comma-separated CORS allowlist |

---

## Project structure

```text
arxiv-rag-assistant/
│
├── app/
│   ├── core/          config, service container, logging, error handling
│   ├── database/      engine and session factory
│   ├── dependencies/  session resolution, rate limits, service injection
│   ├── middleware/    request logging
│   ├── models/        ResearchSession, Paper, Chunk
│   ├── routers/       sessions, ingestion, chat, search
│   ├── schemas/       request and response models
│   └── services/      retrieval, ingestion, embedding, reranking, caching
│
├── docker/
├── tests/
│
├── DESIGN.md
├── docker-compose.yml
├── Dockerfile
├── main.py
└── requirements.txt
```

`DESIGN.md` covers the hosting topology, the free-tier constraints that shaped
the design, and the tradeoffs behind the session model.
