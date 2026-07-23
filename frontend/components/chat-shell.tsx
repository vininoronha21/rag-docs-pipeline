"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Database, Loader2, SendHorizonal, ThumbsDown, ThumbsUp } from "lucide-react";
import { EvidenceBench, EvidencePanel } from "@/components/evidence-panel";
import { useMediaQuery } from "@/lib/use-media-query";
import { askDocs, checkReadiness, sendQueryFeedback } from "@/lib/api";
import type { Evidence, PublicQueryResponse, QueryFeedback, ReadinessResponse } from "@/lib/api";

const readinessDelaysMs = [750, 1500, 3000];
const publicQuestionMaxLength = 1000;
const refusalText =
  "Não encontrei evidências suficientes na documentação indexada para responder com segurança.";

type ReadinessState = "checking" | "ready" | "blocked";

export function ChatShell() {
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(null);
  const [response, setResponse] = useState<PublicQueryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<QueryFeedback | null>(null);
  const [readinessState, setReadinessState] = useState<ReadinessState>("checking");
  const [readinessDetail, setReadinessDetail] = useState("Confirmando disponibilidade da API.");
  const [readinessRun, setReadinessRun] = useState(0);
  const [evidencePanelOpen, setEvidencePanelOpen] = useState(false);
  const [panelEvidence, setPanelEvidence] = useState<Evidence[]>([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);

  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const errorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    async function poll(attempt: number) {
      setReadinessState("checking");
      setReadinessDetail("Acordando a API e validando o índice vetorial.");

      try {
        const readiness = await checkReadiness({ timeoutMs: 5000 });
        if (cancelled) return;

        if (isReady(readiness)) {
          setReadinessState("ready");
          setReadinessDetail("API pronta para consultas públicas.");
          return;
        }

        scheduleNextPoll(attempt);
      } catch (err) {
        if (cancelled) return;
        setReadinessDetail(err instanceof Error ? err.message : "Falha ao confirmar disponibilidade da API.");
        scheduleNextPoll(attempt);
      }
    }

    function scheduleNextPoll(attempt: number) {
      const nextDelay = readinessDelaysMs[attempt];
      if (nextDelay === undefined) {
        setReadinessState("blocked");
        setReadinessDetail("A API ainda não respondeu. Tente novamente para revalidar a disponibilidade.");
        return;
      }

      timeoutId = setTimeout(() => {
        void poll(attempt + 1);
      }, nextDelay);
    }

    void poll(0);

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
      }
    };
  }, [readinessRun]);

  const canAsk = readinessState === "ready" && !busy;
  const sentences = response?.answer?.sentences ?? [];
  const isRefusal = response !== null && (response.insufficient_evidence || sentences.length === 0);

  async function handleQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canAsk || !question.trim()) return;

    const asked = question.trim();
    setQuestion("");
    setSubmittedQuestion(asked);
    setResponse(null);
    setFeedback(null);
    setError(null);
    setBusy(true);
    setEvidencePanelOpen(false);

    try {
      const nextResponse = await askDocs(asked);
      setResponse(nextResponse);

      const defaultCitation =
        nextResponse.answer?.sentences[0]?.citation_id ??
        nextResponse.evidence[0]?.citation_id ??
        null;
      setPanelEvidence(nextResponse.evidence);
      setSelectedEvidenceId(defaultCitation);

      const responseIsRefusal =
        nextResponse.insufficient_evidence || (nextResponse.answer?.sentences.length ?? 0) === 0;
      if (responseIsRefusal && !isDesktop) {
        setEvidencePanelOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar a documentação.");
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedback(nextFeedback: QueryFeedback) {
    if (!response?.event_id) return;

    const previousFeedback = feedback;
    setFeedback(nextFeedback);
    setError(null);

    try {
      await sendQueryFeedback(response.event_id, nextFeedback);
    } catch (err) {
      setFeedback(previousFeedback);
      setError(err instanceof Error ? err.message : "Não foi possível registrar o feedback.");
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  }

  function selectEvidence(evidence: Evidence[], citationId: string | null) {
    setPanelEvidence(evidence);
    setSelectedEvidenceId(citationId);
    if (!isDesktop) {
      setEvidencePanelOpen(true);
    }
  }

  return (
    <main className="min-h-screen bg-paper text-ink">
      <header className="border-b border-line bg-paper/95 px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent text-white">
              <Database size={18} aria-hidden="true" />
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-accent">
                Bancada de evidências
              </p>
              <h1 className="font-serif text-lg font-semibold tracking-tight text-ink">
                RAG Docs Pipeline
              </h1>
            </div>
          </div>
          <div aria-live="polite" className="flex items-center gap-2 text-xs text-ink-soft">
            <span
              className={
                readinessState === "ready"
                  ? "h-2 w-2 rounded-full bg-accent"
                  : readinessState === "blocked"
                    ? "h-2 w-2 rounded-full bg-amber-500"
                    : "h-2 w-2 animate-pulse rounded-full bg-slate-400"
              }
              aria-hidden="true"
            />
            <span>{readinessState === "ready" ? "API pronta" : "Preparando"}</span>
            <span className="sr-only">{readinessDetail}</span>
            {readinessState === "blocked" ? (
              <button
                type="button"
                onClick={() => setReadinessRun((current) => current + 1)}
                className="ml-2 rounded-md border border-line bg-white px-2 py-1 font-medium text-ink outline-none hover:text-accent focus-visible:ring-4 focus-visible:ring-accent/20"
              >
                Tentar novamente
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl grid-cols-1 lg:grid-cols-[1fr_minmax(380px,440px)]">
        <section className="flex min-h-[calc(100vh-64px)] flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
            <div
              className="mx-auto flex max-w-3xl flex-col gap-5"
              aria-live="polite"
              aria-relevant="additions text"
            >
              {!submittedQuestion && !response ? (
                <section className="mt-10 rounded-2xl border border-line bg-white p-6 shadow-sm shadow-black/5 sm:p-8">
                  <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">
                    Consulta pública
                  </p>
                  <h2 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-ink">
                    Pergunte. Leia a resposta. Abra a prova.
                  </h2>
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-soft">
                    As respostas são extrativas: cada frase aponta para uma citação própria, e a
                    evidência ao lado mostra o recorte original da documentação.
                  </p>
                </section>
              ) : null}

              {submittedQuestion ? (
                <article className="self-end rounded-2xl bg-accent px-4 py-3 text-sm leading-6 text-white shadow-sm shadow-black/10">
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-teal-50/80">
                    Pergunta
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">{submittedQuestion}</p>
                </article>
              ) : null}

              {busy ? (
                <article className="rounded-2xl border border-line bg-white px-4 py-4 text-sm leading-6 text-ink-soft shadow-sm shadow-black/5">
                  <div className="flex items-center gap-2">
                    <Loader2 className="animate-spin text-accent" size={16} aria-hidden="true" />
                    Consultando o índice e preparando citações...
                  </div>
                </article>
              ) : null}

              {response ? (
                <article className="rounded-2xl border border-line bg-white px-4 py-4 text-sm leading-7 text-ink shadow-sm shadow-black/5 sm:px-5">
                  <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-line pb-3">
                    <p className="font-serif text-sm font-semibold uppercase tracking-[0.14em] text-accent">
                      Resposta extraída
                    </p>
                    {isRefusal ? (
                      <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
                        Evidência insuficiente
                      </span>
                    ) : null}
                  </div>

                  <div className="space-y-3">
                    {!isRefusal ? (
                      sentences.map((sentence, sentenceIndex) => (
                        <p
                          key={`${response.event_id}-${sentence.citation_id}-${sentenceIndex}`}
                          className="text-base leading-8 text-ink"
                        >
                          <span>{sentence.text}</span>{" "}
                          <button
                            type="button"
                            onClick={() => selectEvidence(response.evidence, sentence.citation_id)}
                            className="inline-flex min-h-[24px] min-w-[24px] translate-y-[-1px] items-center justify-center rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 font-mono text-xs font-semibold text-accent outline-none hover:border-accent/60 hover:bg-white focus-visible:ring-4 focus-visible:ring-accent/20"
                            aria-label={`Inspecionar evidência ${sentence.citation_id}`}
                            aria-pressed={selectedEvidenceId === sentence.citation_id}
                          >
                            [{sentence.citation_id}]
                          </button>
                        </p>
                      ))
                    ) : (
                      <p className="text-base leading-8 text-ink">{refusalText}</p>
                    )}
                  </div>

                  {response && !isRefusal ? (
                    <FeedbackControls feedback={feedback} onFeedback={handleFeedback} />
                  ) : null}
                </article>
              ) : null}
            </div>
          </div>

          <form onSubmit={handleQuestion} className="border-t border-line bg-white/95 p-4">
            <div className="mx-auto flex max-w-3xl flex-col gap-3">
              {error ? (
                <div
                  ref={errorRef}
                  tabIndex={-1}
                  role="alert"
                  className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm leading-6 text-red-700 outline-none"
                >
                  {error}
                </div>
              ) : null}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <label className="flex-1 text-sm font-medium text-ink" htmlFor="public-question">
                  Pergunta para a documentação
                  <textarea
                    id="public-question"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    maxLength={publicQuestionMaxLength}
                    rows={2}
                    disabled={!canAsk}
                    placeholder={
                      readinessState === "ready"
                        ? "Ex.: Como executo o projeto localmente?"
                        : "Aguarde a API ficar pronta para consultar."
                    }
                    className="mt-2 min-h-14 w-full resize-none rounded-lg border border-line px-3 py-2 text-sm font-normal text-ink outline-none ring-accent/20 placeholder:text-ink-soft/60 focus:ring-4 disabled:cursor-not-allowed disabled:bg-paper disabled:text-ink-soft"
                  />
                </label>
                <button
                  type="submit"
                  disabled={!canAsk || !question.trim()}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-semibold text-white outline-none shadow-sm shadow-black/10 hover:bg-teal-800 focus-visible:ring-4 focus-visible:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                  aria-label="Enviar pergunta"
                >
                  {busy ? (
                    <Loader2 className="animate-spin" size={18} aria-hidden="true" />
                  ) : (
                    <SendHorizonal size={18} aria-hidden="true" />
                  )}
                  <span>Enviar</span>
                </button>
              </div>
            </div>
          </form>
        </section>

        {isDesktop ? (
          <aside className="hidden min-h-[calc(100vh-64px)] border-l border-line lg:flex lg:flex-col">
            {response ? (
              <EvidenceBench evidence={panelEvidence} selectedId={selectedEvidenceId} />
            ) : (
              <div className="flex flex-1 flex-col justify-center gap-3 bg-bench px-6 py-10 text-sm leading-6 text-ink-soft">
                <p className="font-serif text-base font-semibold text-ink">Como funciona</p>
                <p>
                  Cada resposta é extraída da documentação indexada. Toda frase carrega uma citação,
                  e a prova aparece aqui: caminho, commit fixado e o trecho exato.
                </p>
              </div>
            )}
          </aside>
        ) : null}
      </div>

      {!isDesktop ? (
        <EvidencePanel
          open={evidencePanelOpen}
          onOpenChange={setEvidencePanelOpen}
          evidence={panelEvidence}
          selectedId={selectedEvidenceId}
        />
      ) : null}
    </main>
  );
}

function FeedbackControls({
  feedback,
  onFeedback
}: {
  feedback: QueryFeedback | null;
  onFeedback: (next: QueryFeedback) => void;
}) {
  return (
    <div className="mt-5 flex items-center gap-2 border-t border-line pt-3">
      <span className="mr-1 text-xs font-medium uppercase tracking-[0.14em] text-ink-soft">
        {feedback ? "Obrigado pelo retorno" : "Feedback"}
      </span>
      <button
        type="button"
        onClick={() => (feedback === 1 ? undefined : onFeedback(1))}
        aria-label="Marcar resposta como útil"
        aria-pressed={feedback === 1}
        className={
          feedback === 1
            ? "flex h-11 w-11 items-center justify-center rounded-md bg-emerald-100 text-emerald-700 outline-none focus-visible:ring-4 focus-visible:ring-emerald-200"
            : "flex h-11 w-11 items-center justify-center rounded-md text-ink-soft outline-none hover:bg-paper focus-visible:ring-4 focus-visible:ring-accent/20"
        }
      >
        <ThumbsUp size={16} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => (feedback === -1 ? undefined : onFeedback(-1))}
        aria-label="Marcar resposta como não útil"
        aria-pressed={feedback === -1}
        className={
          feedback === -1
            ? "flex h-11 w-11 items-center justify-center rounded-md bg-red-100 text-red-700 outline-none focus-visible:ring-4 focus-visible:ring-red-200"
            : "flex h-11 w-11 items-center justify-center rounded-md text-ink-soft outline-none hover:bg-paper focus-visible:ring-4 focus-visible:ring-accent/20"
        }
      >
        <ThumbsDown size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

function isReady(readiness: ReadinessResponse) {
  return readiness.status === "ready" && readiness.database === "ok" && readiness.pgvector === "ok";
}
