import type { Metadata } from "next";

import { Providers } from "@/lib/providers";
import { DEFAULT_THEME, THEME_INIT_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "ArXiv Research Assistant",
  description:
    "Load up to five papers and ask questions with cited answers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme={DEFAULT_THEME} suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint, so there is no
            flash of the default palette on reload. */}
        <script
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
      </head>
      <body className="min-h-screen antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
