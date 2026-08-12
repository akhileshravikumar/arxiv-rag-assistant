# ArXiv RAG Assistant — System Design v2

Target: a publicly reachable URL where anyone can start a research session, load up to
5 papers (arXiv search **or** their own PDF uploads), ask cited questions, download the
papers, and walk away leaving nothing behind.

Everything runs on free tiers. The only metered cost is the OpenAI API.

---

## 1. User flow

```
1. Land on the URL
   └─ backend issues a session_id (UUID), stored in localStorage

2. Choose a source
   ├─ (A) Search arXiv:  type "graph neural networks for molecules"
   │      → 5 results appear instantly (metadata only, no download yet)
   │      → user ticks the ones they want
   └─ (B) Upload PDFs:   drag in up to 5 files
          → filename, size, page count shown for confirmation

3. Confirm → ingestion runs
   └─ live progress: download → extract → chunk → embed → done (per paper)

4. Research
   ├─ References sidebar: 5 papers, always visible
   │   • open on arXiv   • download PDF   • copy BibTeX   • download all
   └─ Chat: ask questions → answer with inline [1] [2] citations
             → clicking a citation scrolls to the source chunk

5. Leave
   └─ session auto-expires after 2h idle; all papers + chunks deleted
      "Start new research" clears immediately
```

---

## 2. Hosting topology

| Layer | Service | Free-tier reality |
|---|---|---|
| Frontend | **Vercel** (Next.js 15, Hobby) | Fine. Deploys from GitHub. |
| Backend | **Render** free web service | 512 MB RAM, 0.1 CPU, **spins down after 15 min idle, ~50 s cold start**, 750 h/mo |
| Database | **Neon** free Postgres + pgvector | 0.5 GB storage, 100 compute-hrs/mo, auto-suspends after 5 min but wakes in <1 s |
| Cache / jobs | **Upstash Redis** free | 256 MB, 500 k commands/month |
| Embeddings + LLM | **OpenAI API** | Metered — the only real cost |

### Two hosting decisions that matter

**Do not use Render's free Postgres.** It expires after 30 days and takes your
project offline. Neon's free tier has no expiry and supports pgvector. This is the
single most important change for a "finished project that stays online."

**Render's 50-second cold start is the worst UX problem in the stack.** Three ways
to handle it, in order of preference:

1. Show a "waking the server up…" state in the UI with a progress hint. Honest, free,
   no side effects.
2. Ping `/health` every 14 minutes from an external cron (cron-job.org). 750 free
   hours/month ≈ 31 days, so one always-on service consumes the entire allowance —
   works only if this is your only Render service.
3. Move the backend to Fly.io (scale-to-zero, ~2 s wake) or Hugging Face Spaces
   (2 vCPU / 16 GB RAM, but Docker Spaces may now require a paid plan — verify first).

---

## 3. Session model

The corpus is per-session and disposable. No login.

### Schema changes

```python
# app/models/session.py  (new)
class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True)  # uuid4
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    question_count: Mapped[int]  = mapped_column(Integer, default=0)  # abuse cap
```

```python
# app/models/paper.py  (modified)
session_id: Mapped[str] = mapped_column(
    ForeignKey("research_sessions.id", ondelete="CASCADE"),
    nullable=False, index=True,
)
source: Mapped[str] = mapped_column(String(16))  # "arxiv" | "upload"
arxiv_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
pdf_url:  Mapped[str | None] = mapped_column(Text, nullable=True)  # now nullable — uploads have none
filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

__table_args__ = (
    UniqueConstraint("session_id", "pdf_url", name="uq_papers_session_pdf_url"),
)
```

**The existing global `UNIQUE` on `pdf_url` must be dropped.** Two sessions researching
the same topic will legitimately want the same paper. Uniqueness becomes
per-session, and `pdf_url` becomes nullable because uploaded PDFs don't have one.

`Chunk` needs no change — it already cascades from `papers`, so deleting a session
deletes papers, which deletes chunks. Session filtering happens through the existing
join to `Paper`.

### Cleanup without a cron job

Free tiers don't give you a scheduler. Instead, run opportunistic cleanup inside
`POST /sessions` — every time someone starts a new session, delete expired ones:

```python
db.execute(
    delete(ResearchSession).where(ResearchSession.expires_at < func.now())
)
```

One line, no infrastructure, and it self-balances: the more traffic you get, the more
often cleanup runs. Also add it to the `/health` handler so the keep-alive ping does
housekeeping.

---

## 4. Dropping the local models

This is what makes the backend fit in 512 MB. Right now `sentence-transformers` pulls
in `torch` (~800 MB installed) plus two model checkpoints (~220 MB). The image is
~2.5 GB and cold start is dominated by model loading.

### Embeddings → OpenAI, keeping the 384-dim column

`text-embedding-3-small` supports a `dimensions` parameter. Request 384 and
**every downstream piece of code stays identical** — `Vector(384)`, the cosine
distance query, the cache-key service, all unchanged.

```python
# app/services/embedding_service.py  (rewritten, same public interface)
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSION = 384

class EmbeddingService:
    def __init__(self, cache_service=None):
        self.client = OpenAI()
        self.cache_service = cache_service

    def embed_documents(self, texts, batch_size=256):
        # OpenAI accepts up to 2048 inputs per request.
        # 5 papers ≈ 250 chunks ≈ one call.
        response = self.client.embeddings.create(
            model=EMBEDDING_MODEL_NAME,
            input=list(texts),
            dimensions=EMBEDDING_DIMENSION,
        )
        return [item.embedding for item in response.data]
```

Two details:

- **Drop the `QUERY_INSTRUCTION` prefix.** `"Represent this sentence for searching
  relevant passages: "` is a BGE-specific convention. OpenAI models are trained
  symmetrically and the prefix actively hurts. Embed queries and documents the same way.
- Keep `EMBEDDING_MODEL_NAME` in the Redis cache key. It already is — so old bge
  vectors won't collide with new ones.

### Reranker → API or removal

The cross-encoder is the other torch dependency. Keep `RerankerService`'s interface
exactly as-is so `retrieval_pipeline.py` never changes, and swap the internals:

```python
class RerankerService:
    def rerank(self, query, candidates, top_k):
        if not self.enabled:                    # no API key → graceful fallback
            return candidates[:top_k]           # RRF order is already decent
        response = cohere_client.rerank(
            model="rerank-v3.5",
            query=query,
            documents=[c["text"] for c in candidates],
            top_n=top_k,
        )
        ...
```

Cohere's trial key is free with a monthly call cap. If you'd rather stay on one
vendor, an LLM reranker with `gpt-4.1-mini` scoring 20 candidates costs about
$0.001/query and needs no new account.

### Result

```
requirements.txt: remove sentence-transformers, celery[redis]
Image size:  ~2.5 GB → ~250 MB
Cold start:  ~60 s → ~5 s   (Render's ~50 s spin-up dominates instead)
RAM at rest: ~450 MB → ~120 MB
```

---

## 5. BM25 must become per-session

**This is the subtlest breakage in the refactor.** `BM25Service` currently builds one
global in-memory index at startup from every chunk in the database. With per-session
corpora that is wrong in three ways: it leaks other sessions' papers into results, it's
empty at boot (and `build_index` *raises* on an empty corpus, which will crash
`lifespan`), and it never sees newly ingested papers.

### Fix: lazy per-session index with an LRU cache

A session has ~250 chunks. Building `BM25Okapi` over that takes single-digit
milliseconds — cheap enough to do on demand.

```python
class BM25Service:
    def __init__(self, phrase_boost=1.5, max_cached_sessions=20):
        self._cache: OrderedDict[str, _SessionIndex] = OrderedDict()

    def get_index(self, db, session_id):
        if session_id in self._cache:
            self._cache.move_to_end(session_id)
            return self._cache[session_id]
        index = self._build_for_session(db, session_id)   # joins Paper on session_id
        self._cache[session_id] = index
        if len(self._cache) > self.max_cached_sessions:
            self._cache.popitem(last=False)
        return index

    def invalidate(self, session_id):        # call at end of every ingestion
        self._cache.pop(session_id, None)

    def search(self, db, session_id, query, top_k=5):
        index = self.get_index(db, session_id)
        if index is None:
            return []                        # empty session → empty results, NOT an exception
```

Also remove the `build_index` call from `lifespan` in `main.py` — there is nothing to
index at boot any more.

**Alternative worth knowing about:** replace `rank_bm25` with Postgres full-text search
(`tsvector` column + GIN index + `ts_rank_cd`). It filters by `session_id` naturally,
holds zero state in the process, and survives restarts and multiple instances. More
code churn now, but it's the version that scales past one server. The LRU approach is
the right call for a beginner-friendly free-tier build; note the tradeoff and move on.

### Dense retrieval

Add one `.where(Paper.session_id == session_id)` to `RetrievalService.dense_search`.
That's the whole change. With ~250 chunks per session, exact search is fast and no
ivfflat/HNSW index is needed — don't add one, it would only hurt recall at this scale.

---

## 6. Ingestion without Celery

Render's free tier can't run a second process, so Celery is out. FastAPI's
`BackgroundTasks` plus job state in Redis covers it.

```
POST /sessions/{sid}/ingest/arxiv   →  202 { job_id }
                                        BackgroundTasks.add_task(run_ingestion, ...)
GET  /jobs/{job_id}                 →  { state, overall_progress, papers: [
                                          { title, stage, progress, error }
                                        ] }
```

Job state is a Redis hash with a 1-hour TTL. The frontend polls every 1.5 s. Polling
also keeps Render awake for the duration of the job, which is convenient.

**Known limitation, worth stating plainly:** if the instance restarts mid-ingestion the
job is lost. There's no free way around this without a worker. Handle it by marking
jobs stale after 5 minutes with no heartbeat and offering a Retry button.

### Pipeline (shared by both input paths)

```
arXiv path                          Upload path
──────────                          ───────────
fetch metadata (arXiv API)          validate: %PDF- magic bytes,
download PDF → /tmp                   ≤10 MB, ≤50 pages, ≤5 files
                                    save → /tmp
        │                                   │
        └───────────────┬───────────────────┘
                        ▼
             extract text (PyMuPDF)
                        ▼
             chunk (1000 chars, 200 overlap)
                        ▼
             embed (one OpenAI call)
                        ▼
             single transaction commit
                        ▼
             bm25_service.invalidate(session_id)
```

For uploads, derive the title from PDF metadata, falling back to the first
non-trivial line of page 1, falling back to the filename. Authors from PDF metadata or
`["Unknown"]`. Let the user rename a paper in the References panel — cheap to build,
and it makes bad extraction a non-issue.

**Timing budget** (5 papers, warm instance): download ~15 s, extract ~5 s, chunk <1 s,
embed ~3 s, commit ~2 s → roughly **25–40 seconds**. Much faster than the
1–3 minutes local models would need, because embedding moved off the box.

---

## 7. Downloading papers

Do the simple thing:

- **arXiv papers** → link straight to `https://arxiv.org/pdf/{arxiv_id}`. Zero storage,
  zero bandwidth, always correct. Render's free tier has no persistent disk, so
  anything in `data/raw/` disappears on restart anyway.
- **Uploaded papers** → the user already has these files. Don't offer re-download.
- **"Download all"** → a client-side helper that opens each arXiv link, or a server
  endpoint that streams a zip by re-fetching from arXiv on demand. Only if you want it.
- **BibTeX export** → `GET /sessions/{sid}/papers/bibtex` returns a `.bib` file built
  from stored metadata. This is the feature researchers will actually use, and it's
  ~20 lines.

`data/raw/` and `data/processed/` become temp-only (`/tmp`), cleared after each
ingestion. Delete the committed sample PDFs from git before deploying — they're dead
weight in the image.

---

## 8. API surface

```
POST   /sessions                          → { session_id, expires_at }
GET    /sessions/{sid}                    → { papers[], question_count, expires_at }
DELETE /sessions/{sid}                    → purge now

GET    /sessions/{sid}/arxiv/search?q=&max_results=5
                                          → 5 candidates, metadata only, no download
POST   /sessions/{sid}/ingest/arxiv       → { arxiv_ids: [...] }  → 202 { job_id }
POST   /sessions/{sid}/ingest/upload      → multipart, ≤5 files   → 202 { job_id }
GET    /jobs/{job_id}                     → progress

GET    /sessions/{sid}/papers             → reference list
GET    /sessions/{sid}/papers/bibtex      → .bib download

POST   /sessions/{sid}/chat               → { question } → answer + sources
```

Every route takes `sid` in the path and validates it exists and hasn't expired via one
dependency — `SessionDep` — mirroring the existing `CurrentUser` pattern.

Keep `/search/dense`, `/search/bm25`, `/search/hybrid`, `/search/reranked` as
session-scoped debug endpoints. They're genuinely useful for demonstrating that the
hybrid pipeline works, and they cost nothing to keep.

---

## 9. What happens to auth and abuse control

There's no login, so `user_id`-based rate limiting has nothing to key on. The existing
auth code (`auth_service`, `token_service`, `password_service`, JWT deps) should stay in
the repo but come out of the request path — it's good work and it's the natural
upgrade path if you ever add accounts.

Replace it with three Redis counters, since an open endpoint hitting your OpenAI key
is a real risk:

| Limit | Value | Key |
|---|---|---|
| Questions per session | 20 | `rl:session:{sid}:questions` |
| Ingestions per session | 2 | `rl:session:{sid}:ingests` |
| New sessions per IP per day | 5 | `rl:ip:{hash}:sessions` |

Hash the IP (`sha256(ip + salt)[:16]`) so you're not storing raw addresses. Set a hard
monthly spend cap in the OpenAI dashboard as the real backstop — rate limits can be
worked around, a billing cap can't.

---

## 10. Frontend structure

```
frontend/
├── app/
│   ├── layout.tsx
│   └── page.tsx                 ← the whole app is one page
├── components/
│   ├── SourcePicker.tsx         ← tab toggle: arXiv search | upload
│   ├── ArxivSearchForm.tsx
│   ├── PdfDropzone.tsx          ← max 5, client-side validation
│   ├── PaperPreviewList.tsx     ← checkboxes, "Ingest 5 papers →"
│   ├── IngestProgress.tsx       ← polls /jobs/{id}
│   ├── ReferencesPanel.tsx      ← sidebar: links, BibTeX, rename
│   ├── ChatPanel.tsx
│   ├── AnswerBubble.tsx         ← parses [1] [2] → clickable
│   ├── SourceCard.tsx           ← title, chunk #, score, preview, expand
│   └── SessionBanner.tsx        ← expiry countdown, "Start new research"
├── lib/
│   ├── api.ts                   ← typed fetch wrapper, injects session_id
│   └── types.ts                 ← mirrors the Pydantic schemas
└── store/
    └── session.ts               ← Zustand: session_id, selected papers
```

- **TanStack Query** for server state, with `refetchInterval` on the job poll —
  it handles the polling lifecycle so you don't write a `useEffect` timer.
- **Zustand** for `session_id` and the selection set, persisted to localStorage.
- **Citation linking** is the detail that makes the demo feel finished: the backend
  already returns `cited_source_numbers` and per-source `cited_in_answer`. Parse
  `[n]` in the answer text, render as buttons, scroll the matching `SourceCard` into
  view and highlight it.
- Add a **"waking up the server"** state to the API wrapper: if the first request
  takes >3 s, show it. Free-tier honesty beats a spinner that looks broken.

CORS on the backend: allow the Vercel domain and `localhost:3000`, nothing else.

---

## 11. Change inventory

| File | Action |
|---|---|
| `app/models/session.py` | **new** — ResearchSession |
| `app/models/paper.py` | add `session_id`, `source`, `arxiv_id`, `filename`; `pdf_url` nullable; drop global unique |
| `app/services/embedding_service.py` | rewrite internals → OpenAI, keep interface, drop query prefix |
| `app/services/reranker_service.py` | rewrite internals → API or no-op, keep interface |
| `app/services/bm25_service.py` | per-session lazy index + LRU + `invalidate()`; empty → `[]` not raise |
| `app/services/retrieval_service.py` | add `session_id` filter |
| `app/services/hybrid_retrieval_service.py` | thread `session_id` through |
| `app/services/retrieval_pipeline.py` | thread `session_id` through |
| `app/services/chat_service.py` | thread `session_id`; add `session_id` to cache key |
| `app/services/ingestion_service.py` | add upload path; write to `/tmp`; per-session dedupe |
| `app/services/upload_service.py` | **new** — PDF validation, title extraction |
| `app/services/session_service.py` | **new** — create, touch, expire, purge |
| `app/routers/sessions.py` | **new** |
| `app/routers/ingestion.py` | rewrite: BackgroundTasks instead of Celery, uncomment in main |
| `app/tasks/`, `app/core/celery_app.py` | delete |
| `app/dependencies/rate_limit.py` | rekey from user to session/IP |
| `main.py` | drop BM25 boot build, add CORS, mount new routers |
| `requirements.txt` | drop `sentence-transformers`, `celery[redis]` |
| `frontend/` | **new** |
| `data/raw/*.pdf` | delete from git |

Roughly 60% of the existing service layer is untouched — the retrieval pipeline,
context builder, answer generation, chunking, PDF extraction, caching, logging, and
error handling all carry over. The refactor is mostly threading one parameter through
and swapping two model backends behind stable interfaces.

---

## 12. Build order

**Phase 0 — backend refactor, no deployment.** Session model, `session_id` threaded
through retrieval, OpenAI embeddings, BM25 per-session. Verify with curl against local
Docker Compose. Update the existing tests — several will break on the new signatures,
and that's the signal that you got the threading right.

**Phase 1 — ingestion.** Upload path, BackgroundTasks jobs, `/jobs/{id}` polling,
arXiv preview endpoint. Still local.

**Phase 2 — deploy the backend.** Neon → Upstash → Render, in that order. Success
criterion: `/docs` loads at a public URL and you can drive the full flow from Swagger UI
with no frontend. **Do not start the frontend until this works** — debugging a cold-start
CORS failure through a React app is miserable.

**Phase 3 — frontend.** Build against the deployed backend from day one. Deploy to
Vercel.

**Phase 4 — polish.** BibTeX, citation click-through, expiry countdown, cold-start
messaging, rate limits, OpenAI spend cap.

---

## 13. Cost and risk

**Per research session** (5 papers, 20 questions):

| Item | Cost |
|---|---|
| Embedding ~250 chunks | ~$0.005 |
| 20 questions × GPT-4.1 (~8k context) | ~$0.40 |
| 20 questions × GPT-4.1-mini | ~$0.03 |

Use `gpt-4.1-mini` for the demo — a 13× saving, and with good retrieval the answer
quality gap on grounded Q&A is small. Make the model an env var so you can compare.

**The three things most likely to go wrong:**

1. **Render cold start** makes the first visit feel broken. Mitigate in the UI, not
   with hope.
2. **Ingestion job lost on restart.** Unavoidable without a worker. Detect stale jobs,
   offer retry.
3. **Neon 0.5 GB fills up** if expiry cleanup silently fails. Chunk text dominates
   (~250 chunks × 1 KB × sessions). Add a paper count and total row count to `/health`
   so you can see it coming.

---

*Sources for free-tier figures:*
[Render free tier](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026) ·
[Render Postgres limits](https://kuberns.com/blogs/render-postgres-pricing-setup-limits/) ·
[Neon plans](https://neon.com/docs/introduction/plans) ·
[Upstash pricing](https://upstash.com/blog/redis-new-pricing) ·
[HF Spaces](https://huggingface.co/docs/hub/en/spaces-overview)
