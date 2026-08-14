"use client";

import { useRef, useState } from "react";

const MAX_BYTES = 15 * 1024 * 1024;

function validate(
  files: File[],
  slots: number,
): { accepted: File[]; problems: string[] } {
  const accepted: File[] = [];
  const problems: string[] = [];

  files.forEach((file) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      problems.push(`${file.name} is not a PDF.`);
    } else if (file.size > MAX_BYTES) {
      problems.push(`${file.name} is larger than 15 MB.`);
    } else if (file.size === 0) {
      problems.push(`${file.name} is empty.`);
    } else {
      accepted.push(file);
    }
  });

  if (accepted.length > slots) {
    problems.push(
      `Only ${slots} slot${slots === 1 ? "" : "s"} left; extra files were dropped.`,
    );
  }

  return { accepted: accepted.slice(0, slots), problems };
}

export function PdfDropzone({
  slots,
  disabled,
  onSelect,
}: {
  slots: number;
  disabled: boolean;
  onSelect: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isOver, setIsOver] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  function handle(fileList: FileList | null) {
    if (!fileList) return;

    const { accepted, problems: found } = validate(
      Array.from(fileList),
      slots,
    );

    setProblems(found);
    if (accepted.length > 0) onSelect(accepted);
  }

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsOver(true);
        }}
        onDragLeave={() => setIsOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsOver(false);
          handle(event.dataTransfer.files);
        }}
        className={`w-full rounded-lg border-2 border-dashed px-6 py-10 text-center disabled:opacity-50 ${
          isOver
            ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
            : "border-[var(--color-line)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-hover)]"
        }`}
      >
        <p className="text-sm font-medium">
          Drop PDFs here, or click to choose
        </p>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Up to {slots} more {slots === 1 ? "paper" : "papers"} · 15 MB
          and 80 pages each
        </p>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        onChange={(event) => {
          handle(event.target.files);
          event.target.value = "";
        }}
      />

      {problems.length > 0 && (
        <ul className="mt-3 space-y-1">
          {problems.map((problem) => (
            <li
              key={problem}
              className="text-xs text-[var(--color-danger)]"
            >
              {problem}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
