import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  adminGetAnalyticsSummary,
  adminIngestGithub,
  adminListSources,
  adminUpdateSource,
  ApiError,
  askDocs,
  checkReadiness,
  sendQueryFeedback
} from "./api";

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

const fetchMock = vi.fn<typeof fetch>();

describe("frontend API client", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("checks readiness through the public readiness endpoint without authorization", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ status: "ready", database: "ok", pgvector: "ok" })
    );

    await expect(checkReadiness()).resolves.toEqual({
      status: "ready",
      database: "ok",
      pgvector: "ok"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/ready",
      expect.objectContaining({ method: "GET" })
    );
    const init = fetchInitAt(0);
    expect(headerValue(init.headers, "Authorization")).toBeNull();
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  test("maps answered query responses to public state flags and sentence-level evidence", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        event_id: "550e8400-e29b-41d4-a716-446655440000",
        state: "answered",
        answer: {
          sentences: [{ text: "Run uvicorn to start the app.", citation_id: "c1" }]
        },
        evidence: [
          {
            citation_id: "c1",
            supported_text: "Run uvicorn to start the app.",
            excerpt: "Use uvicorn main:app --reload during development.",
            title: "FastAPI docs",
            repository_path: "docs/tutorial.md",
            section: "Run it",
            commit_sha: "abc123",
            source_url: "https://github.com/example/repo/blob/abc123/docs/tutorial.md#L1",
            vector_score: 0.82,
            text_score: 0.64,
            fused_score: 0.91
          }
        ],
        metrics: {
          latency_ms: 34,
          retrieved_chunk_count: 3,
          top_fused_score: 0.91,
          score_gap: 0.22
        }
      })
    );

    const response = await askDocs("How do I run it?", { topK: 3, source: "fastapi" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/query",
      expect.objectContaining({ method: "POST" })
    );
    const init = fetchInitAt(0);
    expect(headerValue(init.headers, "Authorization")).toBeNull();
    expect(JSON.parse(String(init.body))).toEqual({
      question: "How do I run it?",
      top_k: 3,
      source: "fastapi"
    });
    expect(response).toMatchObject({
      event_id: "550e8400-e29b-41d4-a716-446655440000",
      state: "answered",
      answered: true,
      insufficient_evidence: false,
      answer: {
        sentences: [{ text: "Run uvicorn to start the app.", citation_id: "c1" }]
      },
      evidence: [
        {
          citation_id: "c1",
          supported_text: "Run uvicorn to start the app.",
          repository_path: "docs/tutorial.md",
          source_url: "https://github.com/example/repo/blob/abc123/docs/tutorial.md#L1"
        }
      ]
    });
  });

  test("maps insufficient-evidence query responses to public state flags", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        event_id: "550e8400-e29b-41d4-a716-446655440001",
        state: "insufficient_evidence",
        answer: null,
        evidence: [],
        metrics: {
          latency_ms: 20,
          retrieved_chunk_count: 0,
          top_fused_score: null,
          score_gap: null
        }
      })
    );

    await expect(askDocs("Is billing supported?")).resolves.toMatchObject({
      event_id: "550e8400-e29b-41d4-a716-446655440001",
      state: "insufficient_evidence",
      answered: false,
      insufficient_evidence: true,
      answer: null
    });
  });

  test("sends UUID feedback through the public query-events path without authorization", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ event_id: "550e8400-e29b-41d4-a716-446655440000", feedback: 1 })
    );

    await expect(sendQueryFeedback("550e8400-e29b-41d4-a716-446655440000", 1)).resolves.toEqual({
      event_id: "550e8400-e29b-41d4-a716-446655440000",
      feedback: 1
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/query-events/550e8400-e29b-41d4-a716-446655440000/feedback",
      expect.objectContaining({ method: "PATCH" })
    );
    const init = fetchInitAt(0);
    expect(headerValue(init.headers, "Authorization")).toBeNull();
    expect(JSON.parse(String(init.body))).toEqual({ feedback: 1 });
  });

  test("includes the Bearer secret on every admin request", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: 7,
          source_type: "github",
          source_config: { repository: "example/repo" },
          last_sync: null,
          enabled: false
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          status: "synchronized",
          repository: "example/repo",
          branch: "main",
          path: "docs",
          commit_sha: "abc123",
          source_id: 7,
          source_version_id: 8,
          documents: [],
          total_chunks: 0
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          document_count: 1,
          chunk_count: 2,
          source_count: 1,
          enabled_source_count: 1,
          query_count: 3,
          average_latency_ms: 4.5,
          positive_feedback_count: 1,
          negative_feedback_count: 0
        })
      );

    await adminListSources("admin-secret");
    await adminUpdateSource("admin-secret", 7, { enabled: false });
    await adminIngestGithub("admin-secret", {
      repo_url: "https://github.com/example/repo",
      branch: "main",
      path: "docs",
      max_files: 25
    });
    await adminGetAnalyticsSummary("admin-secret");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/admin/sources",
      "http://localhost:8000/api/admin/sources/7",
      "http://localhost:8000/api/admin/ingest/github",
      "http://localhost:8000/api/admin/analytics/summary"
    ]);
    for (let index = 0; index < fetchMock.mock.calls.length; index += 1) {
      expect(headerValue(fetchInitAt(index).headers, "Authorization")).toBe("Bearer admin-secret");
    }
  });

  test("turns FastAPI error bodies into a single safe ApiError", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Document source not found." }, { status: 404 }));

    let thrown: unknown;
    try {
      await adminListSources("admin-secret");
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(ApiError);
    expect(thrown).toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Document source not found."
    });
  });
});
