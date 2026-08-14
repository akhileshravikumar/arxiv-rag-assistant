"use client";

import { useEffect, useState } from "react";

import type { ArxivCandidate } from "@/lib/types";

export function PaperPreviewList({
  candidates,
  slots,
  isIngesting,
  onIngest,
  onCancel,
}: {
  candidates: ArxivCandidate[];
  slots: number;
  isIngesting: boolean;
  onIngest: (arxivIds: string[]) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Preselect what fits, skipping anything already in the session.
    const initial = candidates
      .filter((candidate) => !candidate.already_in_session)
      .slice(0, slots)
      .map((candidate) => candidate.arxiv_id);

    setSelected(new Set(initial));
  }, [candidates, slots]);

  function toggle(arxivId: string) {
    setSelected((current) => {
      const next = new Set(current);

      if (next.has(arxivId)) {
        next.delete(arxivId);
      } else if (next.size < slots) {
        next.add(arxivId);
      }

      return next;
    });
  }

  const atCapacity = selected.size >= slots;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">
          {candidates.length} results
        </h2>
        <p className="text-xs text-[var(--color-muted)]">
          {selected.size} of {slots} selected
        </p>
      </div>

      <ul className="space-y-2">
        {candidates.map((candidate) => {
          const isSelected = selected.has(candidate.arxiv_id);
          const isBlocked =
            candidate.already_in_session ||
            (!isSelected && atCapacity);

          return (
            <li key={candidate.arxiv_id}>
              <label
                className={`flex gap-3 rounded-lg border p-4 ${
                  isSelected
                    ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
                    : "border-[var(--color-line)] bg-[var(--color-surface)]"
                } ${
                  isBlocked
                    ? "is-blocked opacity-55"
                    : isSelected
                      ? "cursor-pointer hover:bg-[var(--color-accent-soft-hover)]"
                      : "cursor-pointer hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  disabled={isBlocked || isIngesting}
                  onChange={() => toggle(candidate.arxiv_id)}
                  className="mt-1 size-4 shrink-0 accent-[var(--color-secondary)]"
                />

                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug">
                    {candidate.title}
                  </p>

                  <p className="mt-1 truncate text-xs text-[var(--color-muted)]">
                    {candidate.authors.slice(0, 4).join(", ")}
                    {candidate.authors.length > 4 && " et al."}
                    {candidate.published &&
                      ` · ${candidate.published.slice(0, 10)}`}
                    {" · "}
                    {candidate.arxiv_id}
                  </p>

                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-[var(--color-muted)]">
                    {candidate.summary}
                  </p>

                  {candidate.already_in_session && (
                    <p className="mt-2 text-xs font-medium text-[var(--color-highlight)]">
                      Already in this session
                    </p>
                  )}
                </div>
              </label>
            </li>
          );
        })}
      </ul>

      <div className="flex gap-3">
        <button
          type="button"
          disabled={selected.size === 0 || isIngesting}
          onClick={() => onIngest(Array.from(selected))}
          className="rounded-lg bg-[var(--color-accent)] px-5 py-3 text-sm font-medium text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:hover:bg-[var(--color-accent)]"
        >
          {isIngesting
            ? "Starting…"
            : `Add ${selected.size} paper${selected.size === 1 ? "" : "s"}`}
        </button>

        <button
          type="button"
          onClick={onCancel}
          disabled={isIngesting}
          className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-3 text-sm hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-hover)] disabled:opacity-40"
        >
          Back
        </button>
      </div>
    </div>
  );
}
