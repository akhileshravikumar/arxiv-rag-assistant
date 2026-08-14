"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/lib/api";
import { TERMINAL_JOB_STATES } from "@/lib/types";
import type { JobStatus } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting",
  downloading: "Downloading",
  extracting_text: "Reading PDF",
  creating_paper: "Saving record",
  chunking: "Splitting into passages",
  embedding: "Generating embeddings",
  saving: "Saving",
  completed: "Done",
  skipped: "Already added",
  failed: "Failed",
};

export function IngestProgress({
  jobId,
  onFinished,
}: {
  jobId: string;
  onFinished: (job: JobStatus) => void;
}) {
  const { data: job, error } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId),
    // Polling stops as soon as the job reaches a terminal state.
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state && TERMINAL_JOB_STATES.includes(state)
        ? false
        : 1500;
    },
    // A blip in the job store must not look like a finished job; the
    // work continues server-side either way.
    retry: 5,
    retryDelay: 1500,
  });

  useEffect(() => {
    if (job && TERMINAL_JOB_STATES.includes(job.state)) {
      onFinished(job);
    }
  }, [job, onFinished]);

  if (error) {
    return (
      <p className="text-sm text-[var(--color-danger)]">
        Lost track of this job: {(error as Error).message}
      </p>
    );
  }

  if (!job) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        Starting…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">
            Adding papers
          </h2>
          <span className="text-xs text-[var(--color-muted)]">
            {job.overall_progress}%
          </span>
        </div>

        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-line)]">
          <div
            className="h-full rounded-full bg-[var(--color-highlight)] transition-all duration-500"
            style={{ width: `${job.overall_progress}%` }}
          />
        </div>
      </div>

      <ul className="space-y-2">
        {job.papers.map((paper, index) => (
          <li
            key={`${paper.label}-${index}`}
            className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3 hover:border-[var(--color-line-strong)]"
          >
            <div className="flex items-baseline justify-between gap-4">
              <p className="min-w-0 truncate text-sm">
                {paper.title ?? paper.label}
              </p>
              <span
                className={`shrink-0 text-xs ${
                  paper.error
                    ? "text-[var(--color-danger)]"
                    : "text-[var(--color-muted)]"
                }`}
              >
                {STAGE_LABELS[paper.stage] ?? paper.stage}
              </span>
            </div>

            {paper.error && (
              <p className="mt-1 text-xs text-[var(--color-danger)]">
                {paper.error}
              </p>
            )}
          </li>
        ))}
      </ul>

      {job.state === "stale" && (
        <p className="text-sm text-[var(--color-danger)]">
          {job.error ??
            "The server restarted while this job was running."}
        </p>
      )}
    </div>
  );
}
