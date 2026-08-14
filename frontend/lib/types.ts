// Mirrors app/schemas/*.py. Keep in step with the backend.

export type PaperSource = "arxiv" | "upload";

export interface Paper {
  id: number;
  title: string;
  authors: string[];
  published: string | null;
  source: PaperSource;
  arxiv_id: string | null;
  pdf_url: string | null;
  filename: string | null;
  page_count: number | null;
  created_at: string;
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  expires_at: string;
  paper_count: number;
  chunk_count: number;
  max_papers: number;
  remaining_paper_slots: number;
  question_count: number;
}

export interface SessionDetail extends SessionSummary {
  papers: Paper[];
}

export interface ArxivCandidate {
  arxiv_id: string;
  title: string;
  authors: string[];
  published: string | null;
  summary: string;
  abstract_url: string;
  pdf_url: string | null;
  already_in_session: boolean;
}

export interface ArxivSearchResponse {
  query: string;
  result_count: number;
  results: ArxivCandidate[];
}

export type JobState =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "stale";

export interface JobPaperStatus {
  label: string;
  stage: string;
  progress: number;
  paper_id: number | null;
  title: string | null;
  error: string | null;
}

export interface JobStatus {
  job_id: string;
  session_id: string;
  state: JobState;
  overall_progress: number;
  created_at: string;
  updated_at: string;
  error: string | null;
  papers: JobPaperStatus[];
}

export interface JobSubmission {
  job_id: string;
  state: string;
  status_url: string;
  message: string;
}

export interface ChatSource {
  source_number: number;
  paper_id: number;
  paper_title: string;
  chunk_id: number;
  chunk_index: number;
  reranker_rank: number;
  reranker_score: number;
  cited_in_answer: boolean;
  text_preview: string;
}

export interface ChatResponse {
  question: string;
  answer: string;
  model: string;
  cited_source_numbers: number[];
  sources: ChatSource[];
  context_character_count: number;
  estimated_context_tokens: number;
  cache_hit: boolean;
}

export interface ChatTurn extends ChatResponse {
  id: string;
}

export const TERMINAL_JOB_STATES: JobState[] = [
  "completed",
  "failed",
  "stale",
];
