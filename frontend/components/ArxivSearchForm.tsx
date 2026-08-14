"use client";

import { useState } from "react";

export function ArxivSearchForm({
  onSearch,
  isSearching,
  disabled,
}: {
  onSearch: (query: string) => void;
  isSearching: boolean;
  disabled: boolean;
}) {
  const [query, setQuery] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = query.trim();
        if (trimmed.length >= 2) onSearch(trimmed);
      }}
      className="flex flex-col gap-3 sm:flex-row"
    >
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="What are you researching? e.g. graph neural networks for molecules"
        disabled={disabled}
        className="flex-1 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)] hover:border-[var(--color-line-strong)] focus:border-[var(--color-accent)] disabled:opacity-50"
      />

      <button
        type="submit"
        disabled={disabled || isSearching || query.trim().length < 2}
        className="rounded-lg bg-[var(--color-accent)] px-5 py-3 text-sm font-medium text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:hover:bg-[var(--color-accent)]"
      >
        {isSearching ? "Searching…" : "Search arXiv"}
      </button>
    </form>
  );
}
