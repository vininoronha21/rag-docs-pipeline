import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Docs Pipeline",
  description: "Semantic search and cited answers for fragmented documentation."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
