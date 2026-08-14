"use client";

import { useEffect, useState } from "react";

import { ThemeToggle } from "./ThemeToggle";
import { onSlowRequest } from "@/lib/api";

function remaining(expiresAt: string): string {
  const milliseconds =
    new Date(expiresAt).getTime() - Date.now();

  if (milliseconds <= 0) return "expired";

  const minutes = Math.floor(milliseconds / 60_000);

  if (minutes < 60) return `${minutes}m left`;

  return `${Math.floor(minutes / 60)}h ${minutes % 60}m left`;
}

export function SessionBanner({
  expiresAt,
}: {
  expiresAt: string | null;
}) {
  const [label, setLabel] = useState(() =>
    expiresAt ? remaining(expiresAt) : "",
  );

  const [isWaking, setIsWaking] = useState(false);

  useEffect(() => {
    if (!expiresAt) return;

    setLabel(remaining(expiresAt));

    const timer = setInterval(
      () => setLabel(remaining(expiresAt)),
      30_000,
    );

    return () => clearInterval(timer);
  }, [expiresAt]);

  useEffect(() => onSlowRequest(setIsWaking), []);

  return (
    <header className="border-b border-[var(--color-line)] bg-[var(--color-surface)]">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
        <div>
          <h1 className="text-base font-semibold">
            ArXiv Research Assistant
          </h1>
          <p className="text-xs text-[var(--color-muted)]">
            Up to 5 papers per session · nothing is stored afterwards
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right text-xs text-[var(--color-muted)]">
            {isWaking && (
              <p className="font-medium text-[var(--color-highlight)]">
                Waking the server up…
              </p>
            )}
            {expiresAt && <p>Session {label}</p>}
          </div>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
