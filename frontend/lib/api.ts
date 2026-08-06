export type ReadinessResponse = {
  status: "ready" | "not_ready";
  database: "ok" | "error";
  pgvector: "ok" | "missing" | "error" | "unknown";
};

export type EvidenceState = "answered" | "insufficient_evidence";

export type AnswerSentence = {
  text: string;
  citation_id: string;
};

export type ExtractiveAnswer = {
  sentences: AnswerSentence[];
};

export type Evidence = {
  citation_id: string | null;
  supported_text: string | null;
  excerpt: string;
  title: string | null;
  repository_path: string;
  section: string | null;
  commit_sha: string;
  source_url: string;
  vector_score: number | null;
  text_score: number | null;
  fused_score: number;
};

export type QueryMetrics = {
  latency_ms: number;
  retrieved_chunk_count: number;
  top_fused_score: number | null;
  score_gap: number | null;
};

type QueryApiResponse = {
  event_id: string;
  state: EvidenceState;
  answer: ExtractiveAnswer | null;
  evidence: Evidence[];
  metrics: QueryMetrics;
};

export type PublicQueryResponse = QueryApiResponse & {
  answered: boolean;
  insufficient_evidence: boolean;
};

export type QueryOptions = {
  topK?: number;
  source?: string;
  timeoutMs?: number;
};

export type QueryFeedback = -1 | 1;

export type QueryFeedbackResponse = {
  event_id: string;
  feedback: QueryFeedback;
};

export type GithubIngestRequest = {
  repo_url: string;
  branch?: string | null;
  path: string;
  max_files?: number;
};

export type IngestedDocument = {
  source_url: string;
  title: string | null;
  chunk_count: number;
};

export type IngestResponse = {
  status: "synchronized" | "no_op";
  repository: string;
  branch: string;
  path: string;
  commit_sha: string;
  source_id: number;
  source_version_id: number;
  documents: IngestedDocument[];
  total_chunks: number;
};

export type DocSource = {
  id: number;
  source_type: string;
  source_config: Record<string, unknown>;
  last_sync: string | null;
  enabled: boolean;
  active_version_id: number | null;
  active_commit_sha: string | null;
  active_document_count: number | null;
  active_chunk_count: number | null;
};

export type DocSourceListResponse = {
  items: DocSource[];
};

export type DocSourceUpdateRequest = {
  enabled: boolean;
};

export type AnalyticsSummary = {
  document_count: number;
  chunk_count: number;
  active_document_count: number;
  active_chunk_count: number;
  source_count: number;
  enabled_source_count: number;
  query_count: number;
  average_latency_ms: number;
  positive_feedback_count: number;
  negative_feedback_count: number;
};

type RequestOptions = {
  timeoutMs?: number;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const defaultTimeoutMs = 15000;
const ingestionTimeoutMs = 300000;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function checkReadiness(options: RequestOptions = {}): Promise<ReadinessResponse> {
  return request<ReadinessResponse>("/api/ready", { method: "GET" }, options);
}

export async function askDocs(
  question: string,
  options: QueryOptions = {}
): Promise<PublicQueryResponse> {
  const payload: { question: string; top_k: number; source?: string } = {
    question,
    top_k: options.topK ?? 5
  };
  if (options.source) {
    payload.source = options.source;
  }

  const response = await request<QueryApiResponse>(
    "/api/query",
    {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload)
    },
    { timeoutMs: options.timeoutMs }
  );

  return {
    ...response,
    answered: response.state === "answered",
    insufficient_evidence: response.state === "insufficient_evidence"
  };
}

export async function sendQueryFeedback(
  eventId: string,
  feedback: QueryFeedback,
  options: RequestOptions = {}
): Promise<QueryFeedbackResponse> {
  return request<QueryFeedbackResponse>(
    `/api/query-events/${encodeURIComponent(eventId)}/feedback`,
    {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ feedback })
    },
    options
  );
}

export async function adminListSources(
  secret: string,
  options: RequestOptions = {}
): Promise<DocSourceListResponse> {
  return request<DocSourceListResponse>(
    "/api/admin/sources",
    {
      method: "GET",
      headers: adminHeaders(secret)
    },
    options
  );
}

export async function adminUpdateSource(
  secret: string,
  sourceId: number,
  payload: DocSourceUpdateRequest,
  options: RequestOptions = {}
): Promise<DocSource> {
  return request<DocSource>(
    `/api/admin/sources/${sourceId}`,
    {
      method: "PATCH",
      headers: adminHeaders(secret),
      body: JSON.stringify(payload)
    },
    options
  );
}

export async function adminIngestGithub(
  secret: string,
  payload: GithubIngestRequest,
  options: RequestOptions = {}
): Promise<IngestResponse> {
  return request<IngestResponse>(
    "/api/admin/ingest/github",
    {
      method: "POST",
      headers: adminHeaders(secret),
      body: JSON.stringify(payload)
    },
    { timeoutMs: options.timeoutMs ?? ingestionTimeoutMs }
  );
}

export async function adminGetAnalyticsSummary(
  secret: string,
  options: RequestOptions = {}
): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>(
    "/api/admin/analytics/summary",
    {
      method: "GET",
      headers: adminHeaders(secret)
    },
    options
  );
}

async function request<T>(path: string, init: RequestInit, options: RequestOptions): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? defaultTimeoutMs);

  try {
    const response = await fetch(`${backendUrl}${path}`, {
      ...init,
      signal: controller.signal
    });

    if (!response.ok) {
      throw await buildApiError(response);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (isAbortError(error)) {
      throw new ApiError("Request timed out.", 0);
    }
    throw new ApiError("Request failed.", 0);
  } finally {
    clearTimeout(timeout);
  }
}

async function buildApiError(response: Response): Promise<ApiError> {
  const detail = await safeJson(response);
  return new ApiError(
    extractErrorMessage(detail) ?? `Request failed with status ${response.status}.`,
    response.status,
    detail
  );
}

async function safeJson(response: Response): Promise<unknown> {
  if (!response.headers.get("Content-Type")?.includes("application/json")) {
    return null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) {
    return null;
  }

  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const message = (item as { msg: unknown }).msg;
          return typeof message === "string" ? message : null;
        }
        return null;
      })
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join("; ") : null;
  }
  if (detail && typeof detail === "object" && "msg" in detail) {
    const message = (detail as { msg: unknown }).msg;
    return typeof message === "string" ? message : null;
  }

  return null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json" };
}

function adminHeaders(secret: string): HeadersInit {
  return { ...jsonHeaders(), Authorization: `Bearer ${secret}` };
}
