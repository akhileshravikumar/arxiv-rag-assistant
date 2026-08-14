"use client";

import { useEffect, useState } from "react";

import { DEFAULT_THEME, THEME_STORAGE_KEY } from "@/lib/theme";
import type { Theme } from "@/lib/theme";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      className="size-4"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-4"
      aria-hidden="true"
    >
      <path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2Z" />
    </svg>
  );
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME);

  // The icon depends on a value only the browser knows, so it stays
  // hidden until after hydration to keep the markup matching.
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    const applied = document.documentElement.dataset.theme;
    setTheme(applied === "light" ? "light" : "dark");
    setIsMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";

    setTheme(next);
    document.documentElement.dataset.theme = next;

    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Private browsing can block storage; the theme still applies.
    }
  }

  const label =
    theme === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      aria-pressed={theme === "light"}
      className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-ink)] active:scale-95"
    >
      <span className={isMounted ? "" : "opacity-0"}>
        {theme === "dark" ? <SunIcon /> : <MoonIcon />}
      </span>
    </button>
  );
}
