"use client";

import { useState } from "react";

import { API_URL } from "@/lib/api";
import type { Paper } from "@/lib/types";

function PaperRow({
  paper,
  index,
  onRename,
}: {
  paper: Paper;
  index: number;
  onRename: (paperId: number, title: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(paper.title);

  const arxivLink = paper.arxiv_id
    ? `https://arxiv.org/abs/${paper.arxiv_id}`
    : null;

  return (
    <li className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-3 hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-hover)]">
      <div className="flex gap-2">
        <span className="mt-0.5 shrink-0 text-xs font-semibold text-[var(--color-muted)]">
          {index + 1}
        </span>

        <div className="min-w-0 flex-1">
          {isEditing ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const trimmed = draft.trim();
                if (trimmed) onRename(paper.id, trimmed);
                setIsEditing(false);
              }}
            >
              <input
                autoFocus
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onBlur={() => setIsEditing(false)}
                className="w-full rounded border border-[var(--color-accent)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-ink)] outline-none"
              />
            </form>
          ) : (
            <p className="text-sm font-medium leading-snug">
              {paper.title}
            </p>
          )}

          <p className="mt-1 truncate text-xs text-[var(--color-muted)]">
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 && " et al."}
            {paper.page_count && ` · ${paper.page_count}pp`}
          </p>

          <div className="mt-2 flex flex-wrap gap-3 text-xs">
            {arxivLink && (
              <a
                href={arxivLink}
                target="_blank"
                rel="noreferrer noopener"
                className="text-[var(--color-highlight)] hover:text-[var(--color-highlight-hover)] hover:underline"
              >
                arXiv
              </a>
            )}

            {paper.pdf_url && (
              <a
                href={paper.pdf_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-[var(--color-highlight)] hover:text-[var(--color-highlight-hover)] hover:underline"
              >
                PDF
              </a>
            )}

            {paper.source === "upload" && (
              <span className="text-[var(--color-muted)]">
                Uploaded
              </span>
            )}

            <button
              type="button"
              onClick={() => {
                setDraft(paper.title);
                setIsEditing(true);
              }}
              className="text-[var(--color-muted)] hover:text-[var(--color-ink)] hover:underline"
            >
              Rename
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}

export function ReferencesPanel({
  sessionId,
  papers,
  maxPapers,
  onRename,
  onAddMore,
  onReset,
}: {
  sessionId: string;
  papers: Paper[];
  maxPapers: number;
  onRename: (paperId: number, title: string) => void;
  onAddMore: () => void;
  onReset: () => void;
}) {
  return (
    <aside className="flex h-full flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">References</h2>
        <span className="text-xs text-[var(--color-muted)]">
          {papers.length} / {maxPapers}
        </span>
      </div>

      <ul className="space-y-2">
        {papers.map((paper, index) => (
          <PaperRow
            key={paper.id}
            paper={paper}
            index={index}
            onRename={onRename}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-2 text-sm">
        {papers.length < maxPapers && (
          <button
            type="button"
            onClick={onAddMore}
            className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-2 text-left hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]"
          >
            Add more papers
          </button>
        )}

        {papers.length > 0 && (
          <a
            href={`${API_URL}/sessions/${sessionId}/papers/bibtex`}
            className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-2 hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]"
          >
            Download BibTeX
          </a>
        )}

        <button
          type="button"
          onClick={onReset}
          className="rounded-lg px-4 py-2 text-left text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)]"
        >
          Start new research
        </button>
      </div>
    </aside>
  );
}
