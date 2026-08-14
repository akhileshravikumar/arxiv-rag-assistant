export type Theme = "dark" | "light";

export const DEFAULT_THEME: Theme = "dark";

export const THEME_STORAGE_KEY = "arxiv-rag-theme";

/**
 * Runs before React hydrates so the saved theme is already on <html>
 * for the first paint, avoiding a flash of the default palette.
 *
 * This lives in a plain module (not a "use client" one) because the
 * root layout is a server component and needs the literal string.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k=${JSON.stringify(
  THEME_STORAGE_KEY,
)};var t=localStorage.getItem(k);if(t!=="light"&&t!=="dark"){t=${JSON.stringify(
  DEFAULT_THEME,
)}}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme=${JSON.stringify(
  DEFAULT_THEME,
)}}})();`;
