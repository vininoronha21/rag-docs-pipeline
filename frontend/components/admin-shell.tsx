"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Activity, DatabaseZap, Loader2, LockKeyhole, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import {
  adminGetAnalyticsSummary,
  adminIngestGithub,
  adminListSources,
  adminUpdateSource
} from "@/lib/api";
import type { AnalyticsSummary, DocSource, GithubIngestRequest, IngestResponse } from "@/lib/api";

type LoadState = "idle" | "loading" | "ready" | "error";

const curatedSourceMaxFiles = 500;

export function AdminShell() {
  const adminSessionId = useRef(0);
  const [secretInput, setSecretInput] = useState("");
  const [adminSecret, setAdminSecret] = useState<string | null>(null);
  const [sources, setSources] = useState<DocSource[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [curatedPath, setCuratedPath] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<IngestResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [updatingSourceId, setUpdatingSourceId] = useState<number | null>(null);

  useEffect(() => {
    const secret = adminSecret;
    if (!secret) return;
    const sessionId = adminSessionId.current;

    let cancelled = false;

    async function loadAdminData(secret: string) {
      setLoadState("loading");
      setLoadError(null);

      try {
        const [sourceResponse, analyticsResponse] = await Promise.all([
          adminListSources(secret),
          adminGetAnalyticsSummary(secret)
        ]);
        if (cancelled || !isActiveAdminSession(sessionId)) return;

        setSources(sourceResponse.items);
        setAnalytics(analyticsResponse);
        setLoadState("ready");
      } catch (error) {
        if (cancelled || !isActiveAdminSession(sessionId)) return;

        setSources([]);
        setAnalytics(null);
        setLoadState("error");
        setLoadError(errorMessage(error, "Não foi possível carregar os controles administrativos."));
      }
    }

    void loadAdminData(secret);

    return () => {
      cancelled = true;
    };
  }, [adminSecret]);

  function isActiveAdminSession(sessionId: number): boolean {
    return adminSessionId.current === sessionId;
  }

  const locked = adminSecret === null;
  const secretReady = secretInput.trim().length > 0;
  const sourceFormReady = Boolean(repoUrl.trim() && branch.trim() && curatedPath.trim() && !syncing);

  function handleUnlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextSecret = secretInput.trim();
    if (!nextSecret) return;

    adminSessionId.current += 1;
    setAdminSecret(nextSecret);
    setSecretInput("");
  }

  function handleLogout() {
    adminSessionId.current += 1;
    setAdminSecret(null);
    setSecretInput("");
    setSources([]);
    setAnalytics(null);
    setLoadState("idle");
    setLoadError(null);
    setRepoUrl("");
    setBranch("");
    setCuratedPath("");
    setSyncing(false);
    setSyncResult(null);
    setSyncError(null);
    setUpdatingSourceId(null);
  }

  async function handleSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const secret = adminSecret;
    if (!secret || !sourceFormReady) return;
    const sessionId = adminSessionId.current;

    const payload: GithubIngestRequest = {
      repo_url: repoUrl.trim(),
      branch: branch.trim(),
      path: curatedPath.trim(),
      max_files: curatedSourceMaxFiles
    };

    setSyncing(true);
    setSyncResult(null);
    setSyncError(null);

    try {
      const result = await adminIngestGithub(secret, payload);
      if (!isActiveAdminSession(sessionId)) return;

      setSyncResult(result);

      const [sourceResponse, analyticsResponse] = await Promise.all([
        adminListSources(secret),
        adminGetAnalyticsSummary(secret)
      ]);
      if (!isActiveAdminSession(sessionId)) return;

      setSources(sourceResponse.items);
      setAnalytics(analyticsResponse);
      setLoadState("ready");
      setLoadError(null);
    } catch (error) {
      if (!isActiveAdminSession(sessionId)) return;
      setSyncError(errorMessage(error, "Não foi possível sincronizar a fonte."));
    } finally {
      if (isActiveAdminSession(sessionId)) {
        setSyncing(false);
      }
    }
  }

  async function handleToggleSource(source: DocSource) {
    const secret = adminSecret;
    if (!secret || updatingSourceId !== null) return;
    const sessionId = adminSessionId.current;

    setUpdatingSourceId(source.id);
    setLoadError(null);

    try {
      const updatedSource = await adminUpdateSource(secret, source.id, { enabled: !source.enabled });
      if (!isActiveAdminSession(sessionId)) return;

      setSources((currentSources) =>
        currentSources.map((currentSource) => (currentSource.id === updatedSource.id ? updatedSource : currentSource))
      );

      const analyticsResponse = await adminGetAnalyticsSummary(secret);
      if (!isActiveAdminSession(sessionId)) return;

      setAnalytics(analyticsResponse);
    } catch (error) {
      if (!isActiveAdminSession(sessionId)) return;
      setLoadError(errorMessage(error, "Não foi possível atualizar a fonte."));
    } finally {
      if (isActiveAdminSession(sessionId)) {
        setUpdatingSourceId(null);
      }
    }
  }

  return (
    <main className="min-h-screen bg-surface text-ink">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col lg:grid lg:grid-cols-[360px_1fr]">
        <aside className="border-b border-line bg-slate-950 p-6 text-white lg:border-b-0 lg:border-r lg:border-slate-800">
          <div className="flex h-full flex-col justify-between gap-8">
            <div>
              <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-lg border border-teal-300/30 bg-teal-300/10 text-teal-100">
                <ShieldCheck size={21} aria-hidden="true" />
              </div>
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-teal-200">Console administrativo</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight">RAG Docs Control</h1>
              <p className="mt-4 text-sm leading-6 text-slate-300">
                Operações de ingestão, sincronização e exposição das fontes GitHub indexadas. O segredo é
                temporário e vive só nesta sessão React.
              </p>
            </div>

            <section className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-sm leading-6 text-slate-200">
              <div className="flex items-center gap-2 text-teal-100">
                <LockKeyhole size={16} aria-hidden="true" />
                <p className="font-semibold">{locked ? "Painel bloqueado" : "Sessão administrativa ativa"}</p>
              </div>
              <p className="mt-2 text-slate-300">
                {locked
                  ? "Informe o Bearer secret para carregar fontes e métricas protegidas."
                  : "Ao encerrar a sessão, o segredo sai do estado do componente e os controles voltam ao bloqueio."}
              </p>
            </section>
          </div>
        </aside>

        <section className="flex min-h-screen flex-col px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5">
            {locked ? (
              <form
                onSubmit={handleUnlock}
                className="mt-8 max-w-xl rounded-2xl border border-line bg-white p-6 shadow-sm shadow-slate-900/5 sm:mt-20 sm:p-8"
              >
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">Acesso temporário</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink">Desbloqueie o painel</h2>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  O segredo não é gravado em storage, cookies ou URL. Ele é descartado da tela após a entrada.
                </p>

                <label className="mt-6 block text-sm font-medium text-ink" htmlFor="admin-secret">
                  Segredo administrativo temporário
                  <input
                    id="admin-secret"
                    type="password"
                    value={secretInput}
                    onChange={(event) => setSecretInput(event.target.value)}
                    className="mt-2 h-12 w-full rounded-lg border border-line px-3 text-sm font-normal text-ink outline-none ring-accent/20 placeholder:text-slate-400 focus:ring-4"
                    autoComplete="off"
                    placeholder="Bearer secret"
                  />
                </label>

                <button
                  type="submit"
                  disabled={!secretReady}
                  className="mt-5 inline-flex h-11 items-center justify-center rounded-lg bg-accent px-4 text-sm font-semibold text-white outline-none shadow-sm shadow-teal-900/10 hover:bg-teal-800 focus-visible:ring-4 focus-visible:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Desbloquear painel
                </button>
              </form>
            ) : (
              <>
                <div className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm shadow-slate-900/5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">Operação protegida</p>
                    <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Controle de fontes</h2>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink outline-none hover:border-accent/50 hover:text-accent focus-visible:ring-4 focus-visible:ring-accent/20"
                  >
                    <LogOut size={16} aria-hidden="true" />
                    Encerrar sessão administrativa
                  </button>
                </div>

                {loadError ? (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {loadError}
                  </div>
                ) : null}

                {syncError ? (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    Falha ao sincronizar: {syncError}
                  </div>
                ) : null}

                <MetricsGrid analytics={analytics} loading={loadState === "loading"} />

                <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
                  <form onSubmit={handleSync} className="rounded-2xl border border-line bg-white p-5 shadow-sm shadow-slate-900/5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">Fonte GitHub</p>
                        <h3 className="mt-2 text-xl font-semibold tracking-tight text-ink">Registrar e sincronizar</h3>
                      </div>
                      <span className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-accent">
                        pt-BR
                      </span>
                    </div>

                    <div className="mt-5 grid gap-4 sm:grid-cols-2">
                      <label className="text-sm font-medium text-ink sm:col-span-2" htmlFor="repo-url">
                        URL do repositório GitHub
                        <input
                          id="repo-url"
                          type="url"
                          required
                          value={repoUrl}
                          onChange={(event) => setRepoUrl(event.target.value)}
                          placeholder="https://github.com/org/repo"
                          className="mt-2 h-11 w-full rounded-lg border border-line px-3 text-sm font-normal text-ink outline-none ring-accent/20 placeholder:text-slate-400 focus:ring-4"
                        />
                      </label>
                      <label className="text-sm font-medium text-ink" htmlFor="source-branch">
                        Branch ou tag
                        <input
                          id="source-branch"
                          required
                          value={branch}
                          onChange={(event) => setBranch(event.target.value)}
                          placeholder="main"
                          className="mt-2 h-11 w-full rounded-lg border border-line px-3 text-sm font-normal text-ink outline-none ring-accent/20 placeholder:text-slate-400 focus:ring-4"
                        />
                      </label>
                      <label className="text-sm font-medium text-ink" htmlFor="source-path">
                        Caminho curado
                        <input
                          id="source-path"
                          required
                          value={curatedPath}
                          onChange={(event) => setCuratedPath(event.target.value)}
                          placeholder="docs"
                          className="mt-2 h-11 w-full rounded-lg border border-line px-3 text-sm font-normal text-ink outline-none ring-accent/20 placeholder:text-slate-400 focus:ring-4"
                        />
                      </label>
                    </div>

                    <button
                      type="submit"
                      disabled={!sourceFormReady}
                      className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-semibold text-white outline-none shadow-sm shadow-teal-900/10 hover:bg-teal-800 focus-visible:ring-4 focus-visible:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {syncing ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />}
                      Registrar e sincronizar fonte
                    </button>

                    {syncResult ? <SyncResultCard result={syncResult} /> : null}
                  </form>

                  <section className="rounded-2xl border border-line bg-white p-5 shadow-sm shadow-slate-900/5">
                    <div className="flex items-center gap-2">
                      <DatabaseZap className="text-accent" size={18} aria-hidden="true" />
                      <h3 className="text-lg font-semibold tracking-tight text-ink">Fontes registradas</h3>
                    </div>
                    <div className="mt-4 space-y-3">
                      {loadState === "loading" ? (
                        <p className="text-sm text-slate-600">Carregando fontes protegidas...</p>
                      ) : sources.length > 0 ? (
                        sources.map((source) => (
                          <SourceCard
                            key={source.id}
                            source={source}
                            updating={updatingSourceId === source.id}
                            onToggle={() => void handleToggleSource(source)}
                          />
                        ))
                      ) : (
                        <p className="rounded-lg border border-dashed border-line bg-slate-50 px-3 py-4 text-sm leading-6 text-slate-600">
                          Nenhuma fonte registrada ainda. Use o formulário para registrar e sincronizar a primeira.
                        </p>
                      )}
                    </div>
                  </section>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function MetricsGrid({ analytics, loading }: { analytics: AnalyticsSummary | null; loading: boolean }) {
  const metrics = [
    { label: "documentos ativos", value: analytics?.active_document_count ?? 0 },
    { label: "chunks ativos", value: analytics?.active_chunk_count ?? 0 },
    { label: "fontes", value: analytics?.source_count ?? 0 },
    { label: "fontes ativas", value: analytics?.enabled_source_count ?? 0 },
    { label: "consultas", value: analytics?.query_count ?? 0 }
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Métricas agregadas">
      {metrics.map((metric) => (
        <article key={metric.label} className="rounded-2xl border border-line bg-white p-4 shadow-sm shadow-slate-900/5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">{metric.label}</p>
            {loading ? <Loader2 className="animate-spin text-accent" size={15} aria-hidden="true" /> : <Activity className="text-accent" size={15} aria-hidden="true" />}
          </div>
          <p className="mt-3 text-2xl font-semibold tracking-tight text-ink">
            {formatNumber(metric.value)} {metric.label}
          </p>
        </article>
      ))}
      <article className="rounded-2xl border border-line bg-white p-4 shadow-sm shadow-slate-900/5 sm:col-span-2 xl:col-span-5">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">feedback e latência</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">
          Média {formatNumber(analytics?.average_latency_ms ?? 0)} ms · {formatNumber(analytics?.positive_feedback_count ?? 0)} positivos · {formatNumber(analytics?.negative_feedback_count ?? 0)} negativos
        </p>
      </article>
    </section>
  );
}

function SourceCard({ source, updating, onToggle }: { source: DocSource; updating: boolean; onToggle: () => void }) {
  const repo = sourceConfigString(source, "repo") ?? sourceConfigString(source, "repository") ?? "Repositório não informado";
  const branch = sourceConfigString(source, "branch") ?? "branch não informado";
  const path = sourceConfigString(source, "path") ?? "path não informado";

  return (
    <article className="rounded-xl border border-line bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-ink">{repo}</p>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {branch} · {path}
          </p>
        </div>
        <span
          className={
            source.enabled
              ? "rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700"
              : "rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600"
          }
        >
          {source.enabled ? "Ativa" : "Desativada"}
        </span>
      </div>
      <p className="mt-3 text-xs text-slate-500">Última sincronização: {formatDate(source.last_sync)}</p>
      {source.active_commit_sha ? (
        <div className="mt-3 rounded-lg border border-line bg-white px-3 py-2 text-xs leading-5 text-slate-600">
          <p className="font-medium text-ink">Commit ativo: {source.active_commit_sha}</p>
          <p>
            versão #{source.active_version_id} · {formatNumber(source.active_document_count ?? 0)} documentos · {formatNumber(source.active_chunk_count ?? 0)} chunks
          </p>
        </div>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-line bg-white px-3 py-2 text-xs text-slate-500">
          Sem versão ativa indexada.
        </p>
      )}
      <button
        type="button"
        onClick={onToggle}
        disabled={updating}
        aria-label={`${source.enabled ? "Desativar" : "Ativar"} fonte ${source.id}`}
        className="mt-4 inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink outline-none hover:border-accent/50 hover:text-accent focus-visible:ring-4 focus-visible:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {updating ? <Loader2 className="animate-spin" size={15} aria-hidden="true" /> : null}
        {source.enabled ? "Desativar" : "Ativar"}
      </button>
    </article>
  );
}

function SyncResultCard({ result }: { result: IngestResponse }) {
  return (
    <section className="mt-5 rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm leading-6 text-teal-950" aria-live="polite">
      <p className="font-semibold">Resultado: {result.status}</p>
      <p>Commit ativo: {result.commit_sha}</p>
      <p>{formatNumber(result.total_chunks)} chunks sincronizados</p>
      <p>
        {formatNumber(result.documents.length)} documentos · source #{result.source_id} · versão #{result.source_version_id}
      </p>
    </section>
  );
}

function sourceConfigString(source: DocSource, key: string): string | null {
  const value = source.source_config[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function formatDate(value: string | null): string {
  if (!value) return "nunca";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;

  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
