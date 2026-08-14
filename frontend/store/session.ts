import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SessionState {
  sessionId: string | null;
  /** Job currently being polled, if any. */
  activeJobId: string | null;
  setSessionId: (sessionId: string | null) => void;
  setActiveJobId: (jobId: string | null) => void;
  clear: () => void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: null,
      activeJobId: null,
      setSessionId: (sessionId) => set({ sessionId }),
      setActiveJobId: (activeJobId) => set({ activeJobId }),
      clear: () => set({ sessionId: null, activeJobId: null }),
    }),
    {
      // Survives a reload so a refresh does not abandon the corpus the
      // user just spent a minute ingesting.
      name: "arxiv-rag-session",
    },
  ),
);
