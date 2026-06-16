"use client";

import { FormEvent, useState } from "react";
import { Database, Github, Loader2, SendHorizonal } from "lucide-react";
import { askDocs, ingestGithub, QueryResponse } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: QueryResponse["citations"];
};

export function ChatShell() {
  const [repoUrl, setRepoUrl] = useState("https://github.com/tiangolo/fastapi");
  const [question, setQuestion] = useState("How do I run FastAPI locally?");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState<"ingest" | "query" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleIngest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy("ingest");
    try {
      await ingestGithub(repoUrl, 25);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `Indexed Markdown documentation from ${repoUrl}.`
        }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    const asked = question.trim();
    setMessages((current) => [...current, { role: "user", content: asked }]);
    setQuestion("");
    setError(null);
    setBusy("query");
    try {
      const response = await askDocs(asked);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: response.answer, citations: response.citations }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="min-h-screen bg-surface">
      <div className="mx-auto grid min-h-screen max-w-7xl grid-cols-1 gap-0 lg:grid-cols-[360px_1fr]">
        <aside className="border-b border-line bg-white p-6 lg:border-b-0 lg:border-r">
          <div className="mb-8">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-accent text-white">
              <Database size={20} aria-hidden="true" />
            </div>
            <h1 className="text-2xl font-semibold tracking-normal text-ink">RAG Docs Pipeline</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Index GitHub Markdown into pgvector and ask cited questions against the retrieved context.
            </p>
          </div>

          <form onSubmit={handleIngest} className="space-y-3">
            <label htmlFor="repo" className="text-sm font-medium text-ink">
              GitHub repository
            </label>
            <input
              id="repo"
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none ring-accent/20 focus:ring-4"
            />
            <button
              type="submit"
              disabled={busy !== null}
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "ingest" ? <Loader2 className="animate-spin" size={16} /> : <Github size={16} />}
              Index repository
            </button>
          </form>

          {error ? (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}
        </aside>

        <section className="flex min-h-screen flex-col">
          <div className="flex-1 overflow-y-auto p-6">
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {messages.length === 0 ? (
                <div className="mt-24 border-y border-line py-8">
                  <h2 className="text-xl font-semibold text-ink">Ask the indexed documentation</h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                    Start by indexing a repository, then ask implementation questions and inspect the cited chunks.
                  </p>
                </div>
              ) : null}

              {messages.map((message, index) => (
                <article
                  key={`${message.role}-${index}`}
                  className={
                    message.role === "user"
                      ? "self-end rounded-md bg-accent px-4 py-3 text-sm leading-6 text-white"
                      : "rounded-md border border-line bg-white px-4 py-3 text-sm leading-6 text-slate-800"
                  }
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.citations && message.citations.length > 0 ? (
                    <div className="mt-4 space-y-2 border-t border-line pt-3">
                      {message.citations.slice(0, 3).map((citation, citationIndex) => (
                        <a
                          key={citation.chunk_id}
                          href={citation.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="block text-xs text-slate-600 underline-offset-4 hover:underline"
                        >
                          [{citationIndex + 1}] {citation.title ?? citation.source_url} · score{" "}
                          {citation.score.toFixed(3)}
                        </a>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </div>

          <form onSubmit={handleQuestion} className="border-t border-line bg-white p-4">
            <div className="mx-auto flex max-w-3xl gap-3">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={2}
                className="min-h-12 flex-1 resize-none rounded-md border border-line px-3 py-2 text-sm outline-none ring-accent/20 focus:ring-4"
              />
              <button
                type="submit"
                disabled={busy !== null}
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-accent text-white disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Send question"
              >
                {busy === "query" ? <Loader2 className="animate-spin" size={18} /> : <SendHorizonal size={18} />}
              </button>
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}
