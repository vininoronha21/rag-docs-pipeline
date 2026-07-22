"use client";

import { FormEvent, useState } from "react";
import { Database, ExternalLink, Loader2, SendHorizonal, ThumbsDown, ThumbsUp } from "lucide-react";
import { askDocs, Evidence, PublicQueryResponse, sendQueryFeedback } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  eventId?: string;
  feedback?: -1 | 1;
  evidence?: Evidence[];
  latencyMs?: number;
  retrievedChunkCount?: number;
  insufficientEvidence?: boolean;
};

function answerText(response: PublicQueryResponse) {
  const sentences = response.answer?.sentences ?? [];
  if (sentences.length > 0) {
    return sentences.map((sentence) => sentence.text).join(" ");
  }
  return "I could not find enough evidence in the indexed documentation to answer safely.";
}

function evidenceMetadata(evidence: Evidence) {
  const detail = [evidence.repository_path, evidence.section].filter(Boolean).join(" / ");

  return {
    detail,
    label: evidence.title ?? evidence.repository_path ?? evidence.source_url
  };
}

export function ChatShell() {
  const [question, setQuestion] = useState("How do I run FastAPI locally?");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState<"query" | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          content: answerText(response),
          eventId: response.event_id,
          evidence: response.evidence,
          latencyMs: response.metrics.latency_ms,
          retrievedChunkCount: response.metrics.retrieved_chunk_count,
          insufficientEvidence: response.insufficient_evidence
        }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleFeedback(messageIndex: number, eventId: string, feedback: -1 | 1) {
    const currentFeedback = messages[messageIndex]?.feedback;

    setMessages((current) =>
      current.map((message, index) =>
        index === messageIndex ? { ...message, feedback } : message
      )
    );

    try {
      await sendQueryFeedback(eventId, feedback);
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
              Ask cited questions against the curated documentation index. Administrative ingestion,
              source management, and analytics are no longer exposed from the public experience.
            </p>
          </div>

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
                    Ask an implementation question and inspect the exact evidence returned by the
                    retriever. If evidence is weak, the answer will refuse instead of guessing.
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
                  {message.insufficientEvidence ? (
                    <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                      Insufficient evidence
                    </div>
                  ) : null}
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.role === "assistant" && message.eventId ? (
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleFeedback(index, message.eventId as string, 1)}
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
                        onClick={() => handleFeedback(index, message.eventId as string, -1)}
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
                  {message.role === "assistant" &&
                  (message.latencyMs !== undefined || message.retrievedChunkCount !== undefined) ? (
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                      {message.latencyMs !== undefined ? (
                        <span className="rounded-md bg-slate-100 px-2 py-1">
                          {message.latencyMs}ms
                        </span>
                      ) : null}
                      {message.retrievedChunkCount !== undefined ? (
                        <span className="rounded-md bg-slate-100 px-2 py-1">
                          {message.retrievedChunkCount} chunks
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {message.evidence && message.evidence.length > 0 ? (
                    <div className="mt-4 space-y-2 border-t border-line pt-3">
                      {message.evidence.slice(0, 3).map((evidence, evidenceIndex) => {
                        const metadata = evidenceMetadata(evidence);

                        return (
                          <a
                            key={`${evidence.citation_id ?? evidence.source_url}-${evidenceIndex}`}
                            href={evidence.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="block rounded-md border border-line bg-slate-50 px-3 py-2 text-xs text-slate-600 hover:border-accent/50 hover:bg-white"
                          >
                            <span className="flex items-start justify-between gap-3">
                              <span className="min-w-0">
                                <span className="block truncate font-medium text-ink">
                                  [{evidence.citation_id ?? evidenceIndex + 1}] {metadata.label}
                                </span>
                                {metadata.detail ? (
                                  <span className="mt-1 block line-clamp-2">{metadata.detail}</span>
                                ) : null}
                              </span>
                              <ExternalLink
                                size={14}
                                className="mt-0.5 shrink-0 text-slate-400"
                                aria-hidden="true"
                              />
                            </span>
                            <span className="mt-2 block text-slate-500">
                              score {evidence.fused_score.toFixed(3)}
                            </span>
                          </a>
                        );
                      })}
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
