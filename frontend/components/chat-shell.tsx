"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Clock3,
  Database,
  Github,
  Loader2,
  RefreshCw,
  SendHorizonal,
  ThumbsDown,
  ThumbsUp
} from "lucide-react";
import {
  askDocs,
  getQueryHistory,
  ingestGithub,
  QueryHistoryItem,
  QueryResponse,
  sendQueryFeedback
} from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  queryId?: number;
  feedback?: -1 | 0 | 1;
  citations?: QueryResponse["citations"];
};

export function ChatShell() {
  const [repoUrl, setRepoUrl] = useState("https://github.com/tiangolo/fastapi");
  const [question, setQuestion] = useState("How do I run FastAPI locally?");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState<"ingest" | "query" | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadHistory();
  }, []);

  async function loadHistory() {
    setHistoryBusy(true);
    setHistoryError(null);
    try {
      const response = await getQueryHistory(10);
      setHistory(response.items);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Could not load query history");
    } finally {
      setHistoryBusy(false);
    }
  }

  function restoreHistoryItem(item: QueryHistoryItem) {
    setMessages((current) => [
      ...current,
      { role: "user", content: item.question },
      {
        role: "assistant",
        content: item.answer,
        queryId: item.id,
        feedback: item.feedback ?? undefined
      }
    ]);
  }

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
        {
          role: "assistant",
          content: response.answer,
          queryId: response.query_id,
          citations: response.citations
        }
      ]);
      void loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleFeedback(messageIndex: number, queryId: number, feedback: -1 | 1) {
    const currentFeedback = messages[messageIndex]?.feedback;
    const nextFeedback = currentFeedback === feedback ? 0 : feedback;

    setMessages((current) =>
      current.map((message, index) =>
        index === messageIndex ? { ...message, feedback: nextFeedback } : message
      )
    );

    try {
      await sendQueryFeedback(queryId, nextFeedback);
      setHistory((current) =>
        current.map((item) => (item.id === queryId ? { ...item, feedback: nextFeedback } : item))
      );
    } catch (err) {
      setMessages((current) =>
        current.map((message, index) =>
          index === messageIndex ? { ...message, feedback: currentFeedback } : message
        )
      );
      setError(err instanceof Error ? err.message : "Feedback failed");
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

          <div className="mt-8 border-t border-line pt-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-ink">
                <Clock3 size={16} aria-hidden="true" />
                Query history
              </div>
              <button
                type="button"
                onClick={() => void loadHistory()}
                disabled={historyBusy}
                className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Refresh query history"
              >
                <RefreshCw size={15} className={historyBusy ? "animate-spin" : ""} />
              </button>
            </div>

            {historyError ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {historyError}
              </div>
            ) : null}

            <div className="space-y-2">
              {history.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => restoreHistoryItem(item)}
                  className="block w-full rounded-md border border-line bg-white px-3 py-2 text-left hover:border-accent/50 hover:bg-slate-50"
                >
                  <span className="line-clamp-2 block text-sm font-medium leading-5 text-ink">
                    {item.question}
                  </span>
                  <span className="mt-1 block text-xs text-slate-500">
                    {new Intl.DateTimeFormat(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit"
                    }).format(new Date(item.created_at))}
                  </span>
                </button>
              ))}
            </div>

            {!historyBusy && history.length === 0 && !historyError ? (
              <p className="text-sm leading-6 text-slate-500">Recent answered questions will appear here.</p>
            ) : null}
          </div>
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
                  {message.role === "assistant" && message.queryId ? (
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleFeedback(index, message.queryId as number, 1)}
                        className={
                          message.feedback === 1
                            ? "flex h-8 w-8 items-center justify-center rounded-md bg-emerald-100 text-emerald-700"
                            : "flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
                        }
                        aria-label="Mark answer as helpful"
                      >
                        <ThumbsUp size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleFeedback(index, message.queryId as number, -1)}
                        className={
                          message.feedback === -1
                            ? "flex h-8 w-8 items-center justify-center rounded-md bg-red-100 text-red-700"
                            : "flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
                        }
                        aria-label="Mark answer as not helpful"
                      >
                        <ThumbsDown size={15} />
                      </button>
                    </div>
                  ) : null}
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
