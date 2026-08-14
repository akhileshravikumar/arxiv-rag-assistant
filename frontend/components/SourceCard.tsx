"use client";

import { useState } from "react";

import type { ChatSource } from "@/lib/types";

export function SourceCard({
  source,
  domId,
}: {
  source: ChatSource;
  domId: string;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <li
      id={domId}
      className={`rounded-lg border bg-[var(--color-surface)] p-3 hover:bg-[var(--color-surface-hover)] ${
        source.cited_in_answer
          ? "border-[var(--color-accent)]"
          : "border-[var(--color-line)] hover:border-[var(--color-line-strong)]"
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span className="flex size-5 shrink-0 items-center justify-center rounded bg-[var(--color-accent-soft)] text-xs font-semibold text-[var(--color-highlight)]">
          {source.source_number}
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {source.paper_title}
          </p>

          <p className="mt-0.5 text-xs text-[var(--color-muted)]">
            passage {source.chunk_index} · relevance{" "}
            {source.reranker_score.toFixed(3)}
            {!source.cited_in_answer && " · retrieved, not cited"}
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="mt-2 text-xs text-[var(--color-highlight)] hover:text-[var(--color-highlight-hover)] hover:underline"
      >
        {isOpen ? "Hide passage" : "Show passage"}
      </button>

      {isOpen && (
        <p className="mt-2 rounded bg-[var(--color-canvas)] p-3 text-xs leading-relaxed text-[var(--color-muted)]">
          {source.text_preview}…
        </p>
      )}
    </li>
  );
}
