"""
End-to-end smoke test for the ArXiv RAG Assistant API.

Runs the full user journey against a live backend: create a session,
preview arXiv results, ingest papers, poll the job, upload a PDF, ask a
question, verify the citations resolve, export BibTeX and delete the
session.

Usage:

    # terminal 1
    uvicorn main:app --reload

    # terminal 2
    python -m scripts.smoke_test
    python -m scripts.smoke_test --base-url https://your-app.onrender.com
    python -m scripts.smoke_test --skip-preflight   # HTTP checks only
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()


DEFAULT_BASE_URL = "http://localhost:8000"

# Must match the version declared in main.py. A mismatch means the
# process answering on this port is not the code in this directory.
EXPECTED_API_VERSION = "2.0.0"

# Two short, well-known papers. Small enough to keep the run quick.
SMOKE_ARXIV_IDS = [
    "2005.11401",
    "1706.03762",
]

SMOKE_QUESTION = (
    "What retrieval method is used and what problem does it solve?"
)

JOB_POLL_INTERVAL_SECONDS = 2
JOB_TIMEOUT_SECONDS = 420

# Ingestion runs server-side and is unaffected by a failed poll, so a
# few blips are tolerated before the run is abandoned.
MAX_CONSECUTIVE_POLL_ERRORS = 5


class SmokeTestFailure(Exception):
    """Raised when a check fails and the run cannot continue."""


OPENAI_TIMEOUT_SECONDS = 30
COHERE_TIMEOUT_SECONDS = 20


passed: list[str] = []
failed: list[str] = []
warnings: list[str] = []

_pending_label: str | None = None


def begin(label: str) -> None:
    """
    Print the check name before running it.

    Without this, a hanging network call looks like the script died,
    with no indication of which dependency is unreachable.
    """
    global _pending_label

    _pending_label = label

    print(
        f"  {label:<22} ",
        end="",
        flush=True,
    )


def _emit(
    outcome: str,
    label: str,
    detail: str,
) -> None:
    global _pending_label

    suffix = f"  {detail}" if detail else ""

    if _pending_label == label:
        print(f"{outcome}{suffix}", flush=True)
        _pending_label = None
    else:
        print(
            f"  {label:<22} {outcome}{suffix}",
            flush=True,
        )


def report_pass(label: str, detail: str = "") -> None:
    passed.append(label)
    _emit("PASS", label, detail)


def report_warn(label: str, detail: str = "") -> None:
    warnings.append(label)
    _emit("WARN", label, detail)


def report_fail(label: str, detail: str = "") -> None:
    failed.append(label)
    _emit("FAIL", label, detail)


def section(title: str) -> None:
    print(f"\n{title}", flush=True)
    print("-" * len(title), flush=True)


# ---------------------------------------------------------------------
# Preflight: talk to each dependency directly, so a failure here points
# at configuration rather than at the application.
# ---------------------------------------------------------------------


def preflight_database() -> None:
    begin("PostgreSQL")

    url = os.getenv("DATABASE_URL")

    if not url:
        report_fail(
            "DATABASE_URL",
            "not set",
        )
        return

    if url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            url,
            pool_pre_ping=True,
        )

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

            extension = connection.execute(
                text(
                    "SELECT 1 FROM pg_extension "
                    "WHERE extname = 'vector'"
                )
            ).scalar()

        if extension:
            report_pass(
                "PostgreSQL",
                "connected, pgvector enabled",
            )
        else:
            report_fail(
                "PostgreSQL",
                "connected, but the vector extension is missing. "
                "Run: CREATE EXTENSION IF NOT EXISTS vector;",
            )

    except Exception as exc:
        report_fail(
            "PostgreSQL",
            str(exc)[:200],
        )


def preflight_schema() -> None:
    """
    Check the live schema matches the current models.

    Base.metadata.create_all() creates missing tables but never alters
    existing ones, so a database left over from before the session
    refactor looks fine on connect and then fails on the first insert.
    """
    begin("Schema")

    url = os.getenv("DATABASE_URL")

    if not url:
        report_fail("Schema", "DATABASE_URL is not set")
        return

    if url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    try:
        from sqlalchemy import create_engine, inspect

        inspector = inspect(
            create_engine(url)
        )

        tables = set(
            inspector.get_table_names()
        )

        if "papers" not in tables:
            report_pass(
                "Schema",
                "empty; tables are created at startup",
            )

            return

        columns = {
            column["name"]
            for column in inspector.get_columns(
                "papers"
            )
        }

        stale = []

        if "session_id" not in columns:
            stale.append(
                "papers.session_id is missing"
            )

        if "research_sessions" not in tables:
            stale.append(
                "research_sessions table is missing"
            )

        if "users" in tables:
            stale.append(
                "a users table remains from the old auth schema"
            )

        if not stale:
            report_pass(
                "Schema",
                f"{len(tables)} tables, session-scoped",
            )

            return

        report_fail(
            "Schema",
            "; ".join(stale),
        )

        print(
            "\n        This database predates the session "
            "refactor. Nothing here is worth keeping --\n"
            "        sessions are ephemeral by design. "
            "Drop the old tables:\n\n"
            "          DROP TABLE IF EXISTS chunks CASCADE;\n"
            "          DROP TABLE IF EXISTS papers CASCADE;\n"
            "          DROP TABLE IF EXISTS "
            "research_sessions CASCADE;\n"
            "          DROP TABLE IF EXISTS users CASCADE;\n\n"
            "        They are recreated on next startup.\n"
        )

    except Exception as exc:
        report_fail("Schema", str(exc)[:200])


def preflight_redis() -> None:
    begin("Redis")

    url = os.getenv("REDIS_URL")

    if not url:
        report_fail("REDIS_URL", "not set")
        return

    if "upstash" in url and url.startswith(
        "redis://"
    ):
        report_warn(
            "REDIS_URL",
            "Upstash requires TLS. Use rediss:// not redis://",
        )

    try:
        from redis import Redis

        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        client.ping()

        report_pass("Redis", "connected")

    except Exception as exc:
        report_fail("Redis", str(exc)[:200])


def preflight_openai() -> None:
    begin("OpenAI embeddings")

    if not os.getenv("OPENAI_API_KEY"):
        report_fail(
            "OpenAI embeddings",
            "OPENAI_API_KEY is not set",
        )
        return

    expected_dimension = int(
        os.getenv(
            "EMBEDDING_DIMENSION",
            "384",
        )
    )

    try:
        from openai import OpenAI

        # Without an explicit timeout the client waits ten minutes and
        # retries twice, which looks exactly like a hung script.
        client = OpenAI(
            timeout=OPENAI_TIMEOUT_SECONDS,
            max_retries=1,
        )

        response = client.embeddings.create(
            model=os.getenv(
                "EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
            input=["smoke test"],
            dimensions=expected_dimension,
        )

        length = len(response.data[0].embedding)

        if length == expected_dimension:
            report_pass(
                "OpenAI embeddings",
                f"{length} dimensions",
            )
        else:
            report_fail(
                "OpenAI embeddings",
                f"expected {expected_dimension}, got {length}",
            )

    except Exception as exc:
        report_fail(
            "OpenAI embeddings",
            str(exc)[:200],
        )


def preflight_cohere() -> None:
    begin("Cohere reranker")

    api_key = os.getenv("COHERE_API_KEY")

    if not api_key:
        report_warn(
            "Cohere reranker",
            "no key; retrieval falls back to fusion order",
        )
        return

    try:
        response = requests.post(
            "https://api.cohere.com/v2/rerank",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv(
                    "RERANKER_MODEL",
                    "rerank-v3.5",
                ),
                "query": "retrieval augmented generation",
                "documents": [
                    "A study of protein folding.",
                    "Retrieval-augmented generation "
                    "combines a retriever with a generator.",
                ],
                "top_n": 2,
            },
            timeout=COHERE_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        results = response.json()["results"]

        # The relevant document should win.
        if results[0]["index"] == 1:
            report_pass(
                "Cohere reranker",
                "ranked the relevant passage first",
            )
        else:
            report_warn(
                "Cohere reranker",
                "responded, but ranking looks wrong",
            )

    except Exception as exc:
        report_fail(
            "Cohere reranker",
            str(exc)[:200],
        )


def run_preflight() -> None:
    section("Preflight: dependencies")

    preflight_database()
    preflight_schema()
    preflight_redis()
    preflight_openai()
    preflight_cohere()


# ---------------------------------------------------------------------
# The user journey, over HTTP.
# ---------------------------------------------------------------------


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> requests.Response:
        return self.session.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )

    def expect(
        self,
        method: str,
        path: str,
        expected_status: int,
        label: str,
        **kwargs,
    ) -> requests.Response:
        try:
            response = self.request(
                method,
                path,
                **kwargs,
            )

        except requests.RequestException as exc:
            report_fail(label, str(exc)[:200])

            raise SmokeTestFailure(label) from exc

        if response.status_code != expected_status:
            report_fail(
                label,
                f"HTTP {response.status_code}: "
                f"{response.text[:200]}",
            )

            if response.status_code == 404:
                self.explain_404(
                    method,
                    path,
                )

            raise SmokeTestFailure(label)

        return response

    def explain_404(
        self,
        method: str,
        path: str,
    ) -> None:
        """
        A 404 on a path the API should serve usually means the route was
        never registered, not that a record is missing. Print what the
        app actually exposes so the difference is obvious.
        """
        try:
            schema = self.request(
                "GET",
                "/openapi.json",
            ).json()

        except Exception:
            return

        registered = sorted(
            (verb.upper(), route)
            for route, methods in schema.get(
                "paths",
                {},
            ).items()
            for verb in methods
        )

        info = schema.get("info", {})

        print(
            f"\n        {method} {path} is not "
            f"registered. "
            f"{info.get('title', 'unknown')} "
            f"v{info.get('version', '?')} exposes:",
        )

        for verb, route in registered:
            print(f"          {verb:7} {route}")

        print()


def check_health(client: ApiClient) -> None:
    section("API: health")

    started = time.perf_counter()

    response = client.expect(
        "GET",
        "/health",
        200,
        "GET /health",
    )

    elapsed = time.perf_counter() - started
    body = response.json()

    if body.get("status") == "healthy":
        report_pass(
            "GET /health",
            f"{elapsed:.1f}s, db={body['database']}, "
            f"redis={body['redis']}",
        )
    else:
        report_fail(
            "GET /health",
            f"degraded: db={body.get('database')}, "
            f"redis={body.get('redis')}",
        )

        raise SmokeTestFailure("health")


def check_api_version(client: ApiClient) -> None:
    """
    Confirm the port is serving this codebase.

    Without this, a stale uvicorn process or a leftover Docker container
    holding the port shows up as a series of confusing 404s rather than
    as the one problem it actually is.
    """
    section("API: build identity")

    begin("API build")

    response = client.request(
        "GET",
        "/openapi.json",
    )

    if response.status_code != 200:
        report_fail(
            "API build",
            f"/openapi.json returned "
            f"{response.status_code}",
        )

        raise SmokeTestFailure("API build")

    info = response.json().get("info", {})
    version = info.get("version", "?")
    title = info.get("title", "unknown")

    if version == EXPECTED_API_VERSION:
        report_pass(
            "API build",
            f"{title} v{version}",
        )

        return

    report_fail(
        "API build",
        f"serving v{version}, expected "
        f"v{EXPECTED_API_VERSION}",
    )

    print(
        "\n        The process on this port is running "
        "different code than this directory.\n"
        "        Find and stop it:\n"
        "          Get-Process -Id "
        "(Get-NetTCPConnection -LocalPort 8000)"
        ".OwningProcess\n"
        "          docker ps\n"
    )

    raise SmokeTestFailure("API build")


def create_session(client: ApiClient) -> str:
    section("API: session lifecycle")

    response = client.expect(
        "POST",
        "/sessions",
        201,
        "POST /sessions",
    )

    body = response.json()
    session_id = body["session_id"]

    report_pass(
        "POST /sessions",
        f"id={session_id[:8]}..., "
        f"max_papers={body['max_papers']}",
    )

    return session_id


def search_arxiv(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: arXiv preview")

    started = time.perf_counter()

    response = client.expect(
        "GET",
        f"/sessions/{session_id}/arxiv/search",
        200,
        "GET arxiv/search",
        params={
            "q": "retrieval augmented generation",
            "max_results": 5,
        },
    )

    elapsed = time.perf_counter() - started
    body = response.json()

    if body["result_count"] > 0:
        report_pass(
            "GET arxiv/search",
            f"{body['result_count']} results in "
            f"{elapsed:.1f}s",
        )

        first = body["results"][0]
        print(f"        e.g. {first['title'][:70]}")
    else:
        report_fail(
            "GET arxiv/search",
            "no results returned",
        )


def poll_job(
    client: ApiClient,
    job_id: str,
    label: str,
) -> dict:
    """
    Follow a job to completion.

    A single failed poll is not a failed job -- the work continues on
    the server regardless -- so transient errors are tolerated and only
    a sustained run of them gives up.
    """
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    last_progress = -1
    consecutive_errors = 0

    while time.monotonic() < deadline:
        problem: str | None = None

        try:
            response = client.request(
                "GET",
                f"/jobs/{job_id}",
            )

        except requests.RequestException as exc:
            problem = str(exc)[:120]

        else:
            if response.status_code == 200:
                consecutive_errors = 0

                job = response.json()
                progress = job["overall_progress"]

                if progress != last_progress:
                    stages = ", ".join(
                        f"{paper['label'][:24]}="
                        f"{paper['stage']}"
                        for paper in job["papers"]
                    )

                    print(
                        f"        {progress:3d}%  "
                        f"{stages}",
                        flush=True,
                    )

                    last_progress = progress

                if job["state"] in {
                    "completed",
                    "failed",
                    "stale",
                }:
                    return job

            else:
                problem = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:120]}"
                )

        if problem is not None:
            consecutive_errors += 1

            print(
                f"        poll {consecutive_errors}/"
                f"{MAX_CONSECUTIVE_POLL_ERRORS} "
                f"failed: {problem}",
                flush=True,
            )

            if (
                consecutive_errors
                >= MAX_CONSECUTIVE_POLL_ERRORS
            ):
                report_fail(
                    label,
                    f"{consecutive_errors} consecutive "
                    f"poll failures: {problem}",
                )

                raise SmokeTestFailure(label)

        time.sleep(JOB_POLL_INTERVAL_SECONDS)

    report_fail(
        label,
        f"job did not finish within {JOB_TIMEOUT_SECONDS}s",
    )

    raise SmokeTestFailure(label)


def ingest_arxiv(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: arXiv ingestion")

    started = time.perf_counter()

    response = client.expect(
        "POST",
        f"/sessions/{session_id}/ingest/arxiv",
        202,
        "POST ingest/arxiv",
        json={"arxiv_ids": SMOKE_ARXIV_IDS},
    )

    job_id = response.json()["job_id"]

    report_pass(
        "POST ingest/arxiv",
        f"job={job_id[:8]}...",
    )

    job = poll_job(
        client,
        job_id,
        "arXiv ingestion",
    )

    elapsed = time.perf_counter() - started

    ingested = [
        paper
        for paper in job["papers"]
        if paper["paper_id"] is not None
    ]

    if job["state"] == "completed":
        report_pass(
            "arXiv ingestion",
            f"{len(ingested)}/{len(job['papers'])} papers "
            f"in {elapsed:.0f}s",
        )
    else:
        report_fail(
            "arXiv ingestion",
            f"state={job['state']}, error={job.get('error')}",
        )

    for paper in job["papers"]:
        if paper["error"]:
            report_warn(
                f"  {paper['label']}",
                paper["error"][:120],
            )


def ingest_upload(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: PDF upload ingestion")

    # Fetch a PDF so the upload path is exercised with a real file.
    try:
        pdf_response = requests.get(
            "https://arxiv.org/pdf/1301.3781",
            headers={
                "User-Agent": "ArxivRAGAssistant-SmokeTest/1.0"
            },
            timeout=90,
        )

        pdf_response.raise_for_status()

    except requests.RequestException as exc:
        report_warn(
            "PDF upload",
            f"could not fetch a test PDF: {exc}",
        )

        return

    temporary_pdf = (
        Path(tempfile.gettempdir())
        / "smoke_test_upload.pdf"
    )

    temporary_pdf.write_bytes(
        pdf_response.content
    )

    started = time.perf_counter()

    with temporary_pdf.open("rb") as handle:
        response = client.expect(
            "POST",
            f"/sessions/{session_id}/ingest/upload",
            202,
            "POST ingest/upload",
            files={
                "files": (
                    "word2vec.pdf",
                    handle,
                    "application/pdf",
                )
            },
        )

    job_id = response.json()["job_id"]

    report_pass(
        "POST ingest/upload",
        f"job={job_id[:8]}...",
    )

    job = poll_job(
        client,
        job_id,
        "Upload ingestion",
    )

    elapsed = time.perf_counter() - started

    if job["state"] == "completed":
        title = job["papers"][0]["title"]

        report_pass(
            "Upload ingestion",
            f"{elapsed:.0f}s, title guessed as "
            f"{title[:50]!r}",
        )
    else:
        report_fail(
            "Upload ingestion",
            f"state={job['state']}, error={job.get('error')}",
        )

    temporary_pdf.unlink(missing_ok=True)


def check_papers(
    client: ApiClient,
    session_id: str,
) -> int:
    section("API: reference list")

    response = client.expect(
        "GET",
        f"/sessions/{session_id}/papers",
        200,
        "GET papers",
    )

    papers = response.json()

    report_pass(
        "GET papers",
        f"{len(papers)} in session",
    )

    for paper in papers:
        print(
            f"        [{paper['source']:6}] "
            f"{paper['title'][:60]}"
        )

    return len(papers)


def check_retrieval(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: retrieval stages")

    for stage in (
        "dense",
        "bm25",
        "hybrid",
    ):
        response = client.expect(
            "POST",
            f"/sessions/{session_id}/search/{stage}",
            200,
            f"POST search/{stage}",
            json={
                "query": "retrieval augmented generation",
                "top_k": 5,
            },
        )

        count = response.json()["result_count"]

        if count > 0:
            report_pass(
                f"POST search/{stage}",
                f"{count} results",
            )
        else:
            report_fail(
                f"POST search/{stage}",
                "no results; the session corpus may be empty",
            )


def check_chat(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: chat with citations")

    started = time.perf_counter()

    response = client.expect(
        "POST",
        f"/sessions/{session_id}/chat",
        200,
        "POST chat",
        json={
            "question": SMOKE_QUESTION,
            "candidate_k": 20,
            "final_k": 5,
        },
    )

    elapsed = time.perf_counter() - started
    body = response.json()

    report_pass(
        "POST chat",
        f"{elapsed:.1f}s, model={body['model']}, "
        f"context={body['estimated_context_tokens']} tokens",
    )

    print()
    print(f"        Q: {SMOKE_QUESTION}")
    print(f"        A: {body['answer'][:400]}")
    print()

    cited = body["cited_source_numbers"]
    available = {
        source["source_number"]
        for source in body["sources"]
    }

    if not cited:
        report_warn(
            "Citations",
            "the answer cited no sources",
        )

    elif set(cited).issubset(available):
        report_pass(
            "Citations",
            f"cited {cited}, all resolve to sources",
        )

    else:
        report_fail(
            "Citations",
            f"cited {cited} but only {sorted(available)} exist",
        )

    # A repeat question should be served from the Redis answer cache.
    cached_response = client.expect(
        "POST",
        f"/sessions/{session_id}/chat",
        200,
        "POST chat (cached)",
        json={
            "question": SMOKE_QUESTION,
            "candidate_k": 20,
            "final_k": 5,
        },
    )

    if cached_response.json()["cache_hit"]:
        report_pass(
            "Answer cache",
            "second identical question was a cache hit",
        )
    else:
        report_warn(
            "Answer cache",
            "second identical question missed the cache",
        )


def check_bibtex(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: BibTeX export")

    response = client.expect(
        "GET",
        f"/sessions/{session_id}/papers/bibtex",
        200,
        "GET papers/bibtex",
    )

    entry_count = response.text.count("@article{")

    if entry_count > 0:
        report_pass(
            "GET papers/bibtex",
            f"{entry_count} entries",
        )
    else:
        report_fail(
            "GET papers/bibtex",
            "no entries produced",
        )


def check_session_isolation(
    client: ApiClient,
    populated_session_id: str,
) -> None:
    section("API: session isolation")

    other_session_id = client.expect(
        "POST",
        "/sessions",
        201,
        "POST /sessions (second)",
    ).json()["session_id"]

    response = client.expect(
        "POST",
        f"/sessions/{other_session_id}/search/hybrid",
        200,
        "isolation probe",
        json={
            "query": "retrieval augmented generation",
            "top_k": 5,
        },
    )

    if response.json()["result_count"] == 0:
        report_pass(
            "Session isolation",
            "a fresh session sees none of the other's papers",
        )
    else:
        report_fail(
            "Session isolation",
            "a fresh session returned another session's chunks",
        )

    client.expect(
        "DELETE",
        f"/sessions/{other_session_id}",
        204,
        "DELETE second session",
    )


def check_cleanup(
    client: ApiClient,
    session_id: str,
) -> None:
    section("API: cleanup")

    client.expect(
        "DELETE",
        f"/sessions/{session_id}",
        204,
        "DELETE session",
    )

    report_pass("DELETE session", "204")

    response = client.request(
        "GET",
        f"/sessions/{session_id}",
    )

    if response.status_code == 404:
        report_pass(
            "Session is gone",
            "subsequent GET returns 404",
        )
    else:
        report_fail(
            "Session is gone",
            f"expected 404, got {response.status_code}",
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "End-to-end smoke test for the "
            "ArXiv RAG Assistant API."
        )
    )

    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "SMOKE_TEST_BASE_URL",
            DEFAULT_BASE_URL,
        ),
    )

    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the direct dependency checks.",
    )

    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip the PDF upload path.",
    )

    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="Leave the session in place for manual inspection.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    print("ArXiv RAG Assistant — smoke test")
    print(f"Target: {arguments.base_url}")

    if not arguments.skip_preflight:
        run_preflight()

        if failed:
            print(
                "\nPreflight failed. Fix the above "
                "before running the API checks."
            )

            return 1

    client = ApiClient(arguments.base_url)
    session_id = None

    try:
        check_health(client)
        check_api_version(client)

        session_id = create_session(client)

        search_arxiv(client, session_id)
        ingest_arxiv(client, session_id)

        if not arguments.skip_upload:
            ingest_upload(client, session_id)

        check_papers(client, session_id)
        check_retrieval(client, session_id)
        check_chat(client, session_id)
        check_bibtex(client, session_id)
        check_session_isolation(client, session_id)

        if not arguments.keep_session:
            check_cleanup(client, session_id)

    except SmokeTestFailure as exc:
        print(f"\nStopped early: {exc}")

    except KeyboardInterrupt:
        print("\nInterrupted.")

        return 130

    section("Summary")

    print(f"  passed:   {len(passed)}")
    print(f"  warnings: {len(warnings)}")
    print(f"  failed:   {len(failed)}")

    if warnings:
        print("\n  Warnings:")

        for label in warnings:
            print(f"    - {label}")

    if failed:
        print("\n  Failures:")

        for label in failed:
            print(f"    - {label}")

        if session_id and arguments.keep_session:
            print(
                f"\n  Session kept: {session_id}"
            )

        return 1

    print("\nAll checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
