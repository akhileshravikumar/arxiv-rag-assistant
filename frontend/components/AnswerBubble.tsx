"use client";

import { Fragment } from "react";

// The generation prompt instructs the model to cite as [SOURCE n].
const CITATION_PATTERN = /\[SOURCE\s+(\d+)\]/gi;

export function AnswerBubble({
  answer,
  onCitationClick,
}: {
  answer: string;
  onCitationClick: (sourceNumber: number) => void;
}) {
  const nodes: React.ReactNode[] = [];

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  CITATION_PATTERN.lastIndex = 0;

  while ((match = CITATION_PATTERN.exec(answer)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        <Fragment key={`text-${key}`}>
          {answer.slice(lastIndex, match.index)}
        </Fragment>,
      );
    }

    const sourceNumber = Number(match[1]);

    nodes.push(
      <button
        key={`cite-${key}`}
        type="button"
        onClick={() => onCitationClick(sourceNumber)}
        title={`Jump to source ${sourceNumber}`}
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-[var(--color-accent-soft)] px-1.5 align-baseline text-xs font-semibold text-[var(--color-highlight)] hover:bg-[var(--color-accent)] hover:text-[var(--color-on-accent)]"
      >
        {sourceNumber}
      </button>,
    );

    lastIndex = match.index + match[0].length;
    key += 1;
  }

  if (lastIndex < answer.length) {
    nodes.push(
      <Fragment key={`text-${key}`}>
        {answer.slice(lastIndex)}
      </Fragment>,
    );
  }

  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {nodes}
    </p>
  );
}
