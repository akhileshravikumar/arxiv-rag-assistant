"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { ArxivSearchForm } from "@/components/ArxivSearchForm";
import { ChatPanel } from "@/components/ChatPanel";
import { IngestProgress } from "@/components/IngestProgress";
import { PaperPreviewList } from "@/components/PaperPreviewList";
import { PdfDropzone } from "@/components/PdfDropzone";
import { ReferencesPanel } from "@/components/ReferencesPanel";
import { SessionBanner } from "@/components/SessionBanner";
import { ApiError, api } from "@/lib/api";
import type { ArxivCandidate } from "@/lib/types";
import { useSessionStore } from "@/store/session";

type Mode = "idle" | "preview" | "ingesting";
type SourceKind = "arxiv" | "upload";

export default function Page() {
  const sessionId = useSessionStore((state) => state.sessionId);
  const setSessionId = useSessionStore((state) => state.setSessionId);
  const activeJobId = useSessionStore((state) => state.activeJobId);
  const setActiveJobId = useSessionStore(
    (state) => state.setActiveJobId,
  );

  const queryClient = useQueryClient();

  const [mode, setMode] = useState<Mode>("idle");
  const [sourceKind, setSourceKind] = useState<SourceKind>("arxiv");
  const [candidates, setCandidates] = useState<ArxivCandidate[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  // Zustand rehydrates from localStorage after mount, so wait for that
  // before deciding whether a session needs creating.
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setIsHydrated(useSessionStore.persist.hasHydrated());

    return useSessionStore.persist.onFinishHydration(() =>
      setIsHydrated(true),
    );
  }, []);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId as string),
    enabled: Boolean(sessionId) && isHydrated,
  });

  // useMutation's return value is not referentially stable, so the
  // creation effect must not depend on it or it re-runs every render.
  const isCreatingSession = useRef(false);

  const createSession = useMutation({
    mutationFn: () => api.createSession(),
    onSuccess: (created) => setSessionId(created.session_id),
    onSettled: () => {
      isCreatingSession.current = false;
    },
  });

  const startSession = createSession.mutate;

  // Create a session on first visit, and replace one the server has
  // already expired.
  useEffect(() => {
    if (!isHydrated || isCreatingSession.current) return;

    const expired =
      session.error instanceof ApiError &&
      session.error.isMissingSession;

    if (!sessionId || expired) {
      if (expired) {
        setSessionId(null);
        setActiveJobId(null);
      }

      isCreatingSession.current = true;
      startSession();
    }
  }, [
    isHydrated,
    sessionId,
    session.error,
    startSession,
    setSessionId,
    setActiveJobId,
  ]);

  useEffect(() => {
    if (activeJobId) setMode("ingesting");
  }, [activeJobId]);

  const searchArxiv = useMutation({
    mutationFn: (query: string) =>
      api.searchArxiv(sessionId as string, query, 5),
    onSuccess: (response) => {
      setProblem(
        response.results.length === 0
          ? "No papers matched that search."
          : null,
      );
      setCandidates(response.results);
      if (response.results.length > 0) setMode("preview");
    },
    onError: (error) => setProblem((error as Error).message),
  });

  const startIngest = useMutation({
    mutationFn: (input: string[] | File[]) =>
      typeof input[0] === "string"
        ? api.ingestArxiv(sessionId as string, input as string[])
        : api.ingestUploads(sessionId as string, input as File[]),
    onSuccess: (submission) => {
      setProblem(null);
      setActiveJobId(submission.job_id);
      setMode("ingesting");
    },
    onError: (error) => setProblem((error as Error).message),
  });

  const renamePaper = useMutation({
    mutationFn: ({
      paperId,
      title,
    }: {
      paperId: number;
      title: string;
    }) => api.renamePaper(sessionId as string, paperId, title),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["session", sessionId],
      }),
  });

  const resetSession = useMutation({
    mutationFn: async () => {
      if (sessionId) await api.deleteSession(sessionId);
    },
    onSettled: () => {
      setSessionId(null);
      setActiveJobId(null);
      setCandidates([]);
      setMode("idle");
      queryClient.clear();
    },
  });

  const handleJobFinished = useCallback(() => {
    setActiveJobId(null);
    setCandidates([]);
    setMode("idle");
    queryClient.invalidateQueries({
      queryKey: ["session", sessionId],
    });
  }, [queryClient, sessionId, setActiveJobId]);

  const papers = session.data?.papers ?? [];
  const maxPapers = session.data?.max_papers ?? 5;
  const slots = session.data?.remaining_paper_slots ?? maxPapers;
  const isReady = Boolean(sessionId) && session.isSuccess;

  return (
    <div className="min-h-screen">
      <SessionBanner
        expiresAt={session.data?.expires_at ?? null}
      />

      <main className="mx-auto grid max-w-6xl gap-8 px-6 py-8 lg:grid-cols-[1fr_20rem]">
        <section className="min-w-0 space-y-6">
          {!isReady && (
            <p className="text-sm text-[var(--color-muted)]">
              Starting a research session…
            </p>
          )}

          {isReady && mode === "ingesting" && activeJobId && (
            <IngestProgress
              jobId={activeJobId}
              onFinished={handleJobFinished}
            />
          )}

          {isReady && mode === "preview" && (
            <PaperPreviewList
              candidates={candidates}
              slots={slots}
              isIngesting={startIngest.isPending}
              onIngest={(ids) => startIngest.mutate(ids)}
              onCancel={() => {
                setCandidates([]);
                setMode("idle");
              }}
            />
          )}

          {isReady && mode === "idle" && (
            <div className="space-y-5">
              {slots === 0 ? (
                <p className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
                  This session is full at {maxPapers} papers. Start new
                  research to study a different set.
                </p>
              ) : (
                <>
                  <div className="flex gap-2">
                    {(
                      [
                        ["arxiv", "Search arXiv"],
                        ["upload", "Upload PDFs"],
                      ] as const
                    ).map(([kind, label]) => (
                      <button
                        key={kind}
                        type="button"
                        onClick={() => setSourceKind(kind)}
                        className={`rounded-lg px-4 py-2 text-sm font-medium ${
                          sourceKind === kind
                            ? "bg-[var(--color-accent)] text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)]"
                            : "border border-[var(--color-line)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>

                  {sourceKind === "arxiv" ? (
                    <ArxivSearchForm
                      onSearch={(query) =>
                        searchArxiv.mutate(query)
                      }
                      isSearching={searchArxiv.isPending}
                      disabled={startIngest.isPending}
                    />
                  ) : (
                    <PdfDropzone
                      slots={slots}
                      disabled={startIngest.isPending}
                      onSelect={(files) =>
                        startIngest.mutate(files)
                      }
                    />
                  )}
                </>
              )}

              {problem && (
                <p className="text-sm text-[var(--color-danger)]">
                  {problem}
                </p>
              )}

              {sessionId && (
                <ChatPanel
                  sessionId={sessionId}
                  hasPapers={papers.length > 0}
                />
              )}
            </div>
          )}
        </section>

        {isReady && sessionId && (
          <ReferencesPanel
            sessionId={sessionId}
            papers={papers}
            maxPapers={maxPapers}
            onRename={(paperId, title) =>
              renamePaper.mutate({ paperId, title })
            }
            onAddMore={() => setMode("idle")}
            onReset={() => resetSession.mutate()}
          />
        )}
      </main>
    </div>
  );
}
