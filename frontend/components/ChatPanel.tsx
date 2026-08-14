"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { AnswerBubble } from "./AnswerBubble";
import { SourceCard } from "./SourceCard";
import { api } from "@/lib/api";
import type { ChatTurn } from "@/lib/types";

const SUGGESTIONS = [
  "What problem does each paper set out to solve?",
  "What methods do these papers have in common?",
  "What are the reported limitations?",
];

export function ChatPanel({
  sessionId,
  hasPapers,
}: {
  sessionId: string;
  hasPapers: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  const ask = useMutation({
    mutationFn: (value: string) => api.chat(sessionId, value),
    onSuccess: (response) => {
      setTurns((current) => [
        ...current,
        { ...response, id: crypto.randomUUID() },
      ]);
      setQuestion("");
    },
  });

  const jumpToSource = useCallback(
    (turnId: string, sourceNumber: number) => {
      const element = document.getElementById(
        `source-${turnId}-${sourceNumber}`,
      );

      if (!element) return;

      element.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });

      element.classList.remove("source-flash");
      // Force a reflow so the animation restarts on repeat clicks.
      void element.offsetWidth;
      element.classList.add("source-flash");
    },
    [],
  );

  return (
    <div className="flex flex-col gap-6">
      {turns.length === 0 && hasPapers && (
        <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
          <p className="text-sm font-medium">
            Ask anything about your papers
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Answers cite the passages they came from. Click a citation
            to see the source.
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setQuestion(suggestion)}
                className="rounded-full border border-[var(--color-line)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-ink)]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {turns.map((turn) => (
        <article key={turn.id} className="space-y-3">
          <p className="text-sm font-semibold">{turn.question}</p>

          <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
            <AnswerBubble
              answer={turn.answer}
              onCitationClick={(sourceNumber) =>
                jumpToSource(turn.id, sourceNumber)
              }
            />

            <p className="mt-3 text-xs text-[var(--color-muted)]">
              {turn.model}
              {turn.cache_hit && " · cached"}
              {` · ${turn.estimated_context_tokens} context tokens`}
            </p>
          </div>

          {turn.sources.length > 0 && (
            <ul className="space-y-2">
              {turn.sources.map((source) => (
                <SourceCard
                  key={source.chunk_id}
                  source={source}
                  domId={`source-${turn.id}-${source.source_number}`}
                />
              ))}
            </ul>
          )}
        </article>
      ))}

      {ask.isError && (
        <p className="text-sm text-[var(--color-danger)]">
          {(ask.error as Error).message}
        </p>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = question.trim();
          if (trimmed) ask.mutate(trimmed);
        }}
        className="sticky bottom-0 flex gap-3 bg-[var(--color-canvas)] py-4"
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={
            hasPapers
              ? "Ask a question…"
              : "Add papers before asking questions"
          }
          disabled={!hasPapers || ask.isPending}
          className="flex-1 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)] hover:border-[var(--color-line-strong)] focus:border-[var(--color-accent)] disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={!hasPapers || ask.isPending || !question.trim()}
          className="rounded-lg bg-[var(--color-accent)] px-5 py-3 text-sm font-medium text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:hover:bg-[var(--color-accent)]"
        >
          {ask.isPending ? "Thinking…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
