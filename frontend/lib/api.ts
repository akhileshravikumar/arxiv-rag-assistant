import type {
  ArxivSearchResponse,
  ChatResponse,
  JobStatus,
  JobSubmission,
  Paper,
  SessionDetail,
  SessionSummary,
} from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

// A free-tier instance sleeps after 15 minutes and takes up to a minute
// to wake. Anything slower than this is assumed to be a cold start so
// the UI can say so rather than showing a spinner that looks broken.
const SLOW_REQUEST_MS = 3000;

type SlowListener = (slow: boolean) => void;

const slowListeners = new Set<SlowListener>();
let inFlightSlowRequests = 0;

export function onSlowRequest(listener: SlowListener): () => void {
  slowListeners.add(listener);
  return () => slowListeners.delete(listener);
}

function announceSlow(slow: boolean) {
  slowListeners.forEach((listener) => listener(slow));
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  /** The session expired or was deleted server-side. */
  get isMissingSession(): boolean {
    return this.status === 404;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = `Request failed with status ${response.status}`;
  let code: string | null = null;

  try {
    const body = await response.json();

    // The backend wraps errors as { error: { code, message, ... } },
    // but FastAPI's own 404s use { detail }.
    if (body?.error?.message) {
      message = body.error.message;
      code = body.error.code ?? null;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    // Response had no JSON body; keep the status-based message.
  }

  return new ApiError(message, response.status, code);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const timer = setTimeout(() => {
    inFlightSlowRequests += 1;
    announceSlow(true);
  }, SLOW_REQUEST_MS);

  let markedSlow = false;

  try {
    const response = await fetch(`${API_URL}${path}`, init);

    markedSlow = inFlightSlowRequests > 0;

    if (!response.ok) {
      throw await toApiError(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const contentType = response.headers.get("Content-Type") ?? "";

    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }

    return (await response.text()) as T;
  } finally {
    clearTimeout(timer);

    if (markedSlow) {
      inFlightSlowRequests = Math.max(inFlightSlowRequests - 1, 0);

      if (inFlightSlowRequests === 0) {
        announceSlow(false);
      }
    }
  }
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  createSession(): Promise<SessionSummary> {
    return request<SessionSummary>("/sessions", { method: "POST" });
  },

  getSession(sessionId: string): Promise<SessionDetail> {
    return request<SessionDetail>(`/sessions/${sessionId}`);
  },

  deleteSession(sessionId: string): Promise<void> {
    return request<void>(`/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  searchArxiv(
    sessionId: string,
    query: string,
    maxResults = 5,
  ): Promise<ArxivSearchResponse> {
    const params = new URLSearchParams({
      q: query,
      max_results: String(maxResults),
    });

    return request<ArxivSearchResponse>(
      `/sessions/${sessionId}/arxiv/search?${params}`,
    );
  },

  ingestArxiv(
    sessionId: string,
    arxivIds: string[],
  ): Promise<JobSubmission> {
    return request<JobSubmission>(
      `/sessions/${sessionId}/ingest/arxiv`,
      json({ arxiv_ids: arxivIds }),
    );
  },

  ingestUploads(
    sessionId: string,
    files: File[],
  ): Promise<JobSubmission> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));

    return request<JobSubmission>(
      `/sessions/${sessionId}/ingest/upload`,
      { method: "POST", body: form },
    );
  },

  getJob(jobId: string): Promise<JobStatus> {
    return request<JobStatus>(`/jobs/${jobId}`);
  },

  listPapers(sessionId: string): Promise<Paper[]> {
    return request<Paper[]>(`/sessions/${sessionId}/papers`);
  },

  renamePaper(
    sessionId: string,
    paperId: number,
    title: string,
  ): Promise<Paper> {
    return request<Paper>(
      `/sessions/${sessionId}/papers/${paperId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      },
    );
  },

  getBibtex(sessionId: string): Promise<string> {
    return request<string>(`/sessions/${sessionId}/papers/bibtex`);
  },

  chat(sessionId: string, question: string): Promise<ChatResponse> {
    return request<ChatResponse>(
      `/sessions/${sessionId}/chat`,
      json({ question, candidate_k: 20, final_k: 5 }),
    );
  },
};
