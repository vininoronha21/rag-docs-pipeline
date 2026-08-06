import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { AdminShell } from "./admin-shell";

const fetchMock = vi.fn<typeof fetch>();

const existingSource = {
  id: 3,
  source_type: "github",
  source_config: { repo: "example/project", branch: "main", path: "docs" },
  last_sync: "2026-07-21T12:00:00Z",
  enabled: true,
  active_version_id: 8,
  active_commit_sha: "abc123def456",
  active_document_count: 10,
  active_chunk_count: 70
};

const analyticsSummary = {
  document_count: 12,
  chunk_count: 84,
  active_document_count: 10,
  active_chunk_count: 70,
  source_count: 1,
  enabled_source_count: 1,
  query_count: 9,
  average_latency_ms: 38.5,
  positive_feedback_count: 4,
  negative_feedback_count: 1
};

const refreshedAnalyticsSummary = {
  ...analyticsSummary,
  document_count: 13,
  chunk_count: 91,
  active_document_count: 11,
  active_chunk_count: 77,
  enabled_source_count: 0
};

const emptyAnalyticsSummary = {
  ...analyticsSummary,
  document_count: 0,
  chunk_count: 0,
  active_document_count: 0,
  active_chunk_count: 0,
  source_count: 0,
  enabled_source_count: 0
};

const syncResult = {
  status: "synchronized",
  repository: "example/project",
  branch: "main",
  path: "docs",
  commit_sha: "abc123def456",
  source_id: 3,
  source_version_id: 8,
  documents: [{ source_url: "https://github.com/example/project/blob/abc123def456/docs/index.md", title: "Docs", chunk_count: 7 }],
  total_chunks: 7
};

const canonicalSyncedSource = {
  ...existingSource,
  last_sync: null,
  enabled: false
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json", ...init.headers }
  });
}

function fetchInitAt(index: number): RequestInit {
  const init = fetchMock.mock.calls[index]?.[1];
  if (!init) throw new Error(`Missing fetch init at call ${index}`);
  return init;
}

function headerValue(headers: HeadersInit | undefined, name: string): string | null {
  if (!headers) return null;
  return new Headers(headers).get(name);
}

function requestBodyAt(index: number): unknown {
  return JSON.parse(String(fetchInitAt(index).body));
}

function spyOnPersistence() {
  return [
    vi.spyOn(Storage.prototype, "getItem"),
    vi.spyOn(Storage.prototype, "setItem"),
    vi.spyOn(Storage.prototype, "removeItem"),
    vi.spyOn(Storage.prototype, "clear")
  ];
}

function expectNoSecretPersistence(secret: string, spies: ReturnType<typeof spyOnPersistence>) {
  for (const spy of spies) {
    expect(spy).not.toHaveBeenCalled();
  }
  expect(document.cookie).not.toContain(secret);
  expect(window.location.href).not.toContain(secret);
}

async function unlockAdmin(secret: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Segredo administrativo temporário"), secret);
  await user.click(screen.getByRole("button", { name: "Desbloquear painel" }));
  return user;
}

describe("AdminShell", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState(null, "", "/admin");
    document.cookie = "control_room_marker=present";
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  test("keeps the admin surface locked without making requests before secret entry", () => {
    const spies = spyOnPersistence();

    render(<AdminShell />);

    expect(screen.getByText("Painel bloqueado")).toBeVisible();
    expect(screen.getByLabelText("Segredo administrativo temporário")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Desbloquear painel" })).toBeDisabled();
    expect(screen.queryByText("Controle de fontes")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expectNoSecretPersistence("temporary-admin-secret", spies);
  });

  test("uses the entered secret only in Bearer requests while registering and syncing a pt-BR source", async () => {
    const spies = spyOnPersistence();
    const secret = "temporary-admin-secret";
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [existingSource] }))
      .mockResolvedValueOnce(jsonResponse(analyticsSummary))
      .mockResolvedValueOnce(jsonResponse(syncResult))
      .mockResolvedValueOnce(jsonResponse({ items: [canonicalSyncedSource] }))
      .mockResolvedValueOnce(jsonResponse(refreshedAnalyticsSummary));

    render(<AdminShell />);
    const user = await unlockAdmin(secret);

    expect(await screen.findByText("example/project")).toBeVisible();
    expect(screen.getByText("10 documentos ativos")).toBeVisible();
    expect(screen.getByText("70 chunks ativos")).toBeVisible();
    expect(screen.getByText("Commit ativo: abc123def456")).toBeVisible();
    expect(screen.getByText("versão #8 · 10 documentos · 70 chunks")).toBeVisible();
    expect(screen.getByText("pt-BR")).toBeVisible();

    await user.type(screen.getByLabelText("URL do repositório GitHub"), "https://github.com/example/project");
    await user.type(screen.getByLabelText("Branch ou tag"), "main");
    await user.type(screen.getByLabelText("Caminho curado"), "docs");
    await user.click(screen.getByRole("button", { name: "Registrar e sincronizar fonte" }));

    expect(await screen.findByText("Sincronização concluída")).toBeVisible();
    expect(screen.getAllByText("Commit ativo: abc123def456")).toHaveLength(2);
    expect(screen.getByText("7 chunks sincronizados")).toBeVisible();
    expect(await screen.findByText("11 documentos ativos")).toBeVisible();
    expect(screen.getByText("77 chunks ativos")).toBeVisible();
    expect(screen.getByText("0 fontes ativas")).toBeVisible();
    expect(screen.getByText("Desativada")).toBeVisible();
    expect(screen.getByText("Última sincronização: nunca")).toBeVisible();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/admin/sources",
      "http://localhost:8000/api/admin/analytics/summary",
      "http://localhost:8000/api/admin/ingest/github",
      "http://localhost:8000/api/admin/sources",
      "http://localhost:8000/api/admin/analytics/summary"
    ]);
    for (let index = 0; index < fetchMock.mock.calls.length; index += 1) {
      expect(headerValue(fetchInitAt(index).headers, "Authorization")).toBe(`Bearer ${secret}`);
    }
    expect(requestBodyAt(2)).toEqual({
      repo_url: "https://github.com/example/project",
      branch: "main",
      path: "docs",
      max_files: 500
    });
    expect(screen.queryByDisplayValue(secret)).not.toBeInTheDocument();
    expectNoSecretPersistence(secret, spies);
  });

  test("uses the active secret for enablement controls and logout returns to a cleared locked state", async () => {
    const spies = spyOnPersistence();
    const secret = "temporary-admin-secret";
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [existingSource] }))
      .mockResolvedValueOnce(jsonResponse(analyticsSummary))
      .mockResolvedValueOnce(jsonResponse({ ...existingSource, enabled: false }))
      .mockResolvedValueOnce(jsonResponse({ ...analyticsSummary, enabled_source_count: 0 }));

    render(<AdminShell />);
    const user = await unlockAdmin(secret);

    await user.click(await screen.findByRole("button", { name: "Desativar fonte 3" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(headerValue(fetchInitAt(2).headers, "Authorization")).toBe(`Bearer ${secret}`);
    expect(fetchMock.mock.calls[2]?.[0]).toBe("http://localhost:8000/api/admin/sources/3");
    expect(requestBodyAt(2)).toEqual({ enabled: false });
    expect(fetchMock.mock.calls[3]?.[0]).toBe("http://localhost:8000/api/admin/analytics/summary");
    expect(headerValue(fetchInitAt(3).headers, "Authorization")).toBe(`Bearer ${secret}`);
    expect(await screen.findByText("Desativada")).toBeVisible();
    expect(screen.getByText("0 fontes ativas")).toBeVisible();

    fetchMock.mockClear();
    await user.click(screen.getByRole("button", { name: "Encerrar sessão administrativa" }));

    expect(screen.getByText("Painel bloqueado")).toBeVisible();
    expect(screen.getByLabelText("Segredo administrativo temporário")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Desbloquear painel" })).toBeDisabled();
    expect(screen.queryByText("example/project")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expectNoSecretPersistence(secret, spies);
  });

  test("ignores a stale sync result after logout and a newer admin session", async () => {
    const syncRequest = deferred<Response>();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [existingSource] }))
      .mockResolvedValueOnce(jsonResponse(analyticsSummary))
      .mockReturnValueOnce(syncRequest.promise)
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse(emptyAnalyticsSummary));

    render(<AdminShell />);
    const user = await unlockAdmin("old-admin-secret");

    expect(await screen.findByText("example/project")).toBeVisible();
    await user.type(screen.getByLabelText("URL do repositório GitHub"), "https://github.com/example/project");
    await user.type(screen.getByLabelText("Branch ou tag"), "main");
    await user.type(screen.getByLabelText("Caminho curado"), "docs");
    await user.click(screen.getByRole("button", { name: "Registrar e sincronizar fonte" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    await user.click(screen.getByRole("button", { name: "Encerrar sessão administrativa" }));
    await act(async () => {
      syncRequest.resolve(jsonResponse(syncResult));
      await syncRequest.promise;
      await Promise.resolve();
    });

    await unlockAdmin("new-admin-secret");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(await screen.findByText("Nenhuma fonte registrada ainda. Use o formulário para registrar e sincronizar a primeira.")).toBeVisible();
    expect(screen.queryByText("Sincronização concluída")).not.toBeInTheDocument();
    expect(screen.queryByText("Commit ativo: abc123def456")).not.toBeInTheDocument();
    expect(screen.queryByText("example/project")).not.toBeInTheDocument();
    expect(headerValue(fetchInitAt(0).headers, "Authorization")).toBe("Bearer old-admin-secret");
    expect(headerValue(fetchInitAt(2).headers, "Authorization")).toBe("Bearer old-admin-secret");
    expect(headerValue(fetchInitAt(3).headers, "Authorization")).toBe("Bearer new-admin-secret");
    expect(headerValue(fetchInitAt(4).headers, "Authorization")).toBe("Bearer new-admin-secret");
  });

  test("ignores stale enablement errors after logout and a newer admin session", async () => {
    const updateRequest = deferred<Response>();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [existingSource] }))
      .mockResolvedValueOnce(jsonResponse(analyticsSummary))
      .mockReturnValueOnce(updateRequest.promise)
      .mockResolvedValueOnce(jsonResponse({ items: [existingSource] }))
      .mockResolvedValueOnce(jsonResponse(analyticsSummary));

    render(<AdminShell />);
    const user = await unlockAdmin("old-admin-secret");

    await user.click(await screen.findByRole("button", { name: "Desativar fonte 3" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    await user.click(screen.getByRole("button", { name: "Encerrar sessão administrativa" }));

    await unlockAdmin("new-admin-secret");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(await screen.findByText("example/project")).toBeVisible();

    await act(async () => {
      updateRequest.resolve(jsonResponse({ detail: "Expired secret" }, { status: 403 }));
      await updateRequest.promise;
      await Promise.resolve();
    });

    expect(screen.queryByText("Expired secret")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(headerValue(fetchInitAt(2).headers, "Authorization")).toBe("Bearer old-admin-secret");
    expect(headerValue(fetchInitAt(3).headers, "Authorization")).toBe("Bearer new-admin-secret");
    expect(headerValue(fetchInitAt(4).headers, "Authorization")).toBe("Bearer new-admin-secret");
  });
});
