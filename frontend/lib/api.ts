export type Citation = {
  chunk_id: number;
  title: string | null;
  source_url: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type QueryResponse = {
  query_id: number;
  answer: string;
  citations: Citation[];
  retrieved_chunk_ids: number[];
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export async function askDocs(question: string): Promise<QueryResponse> {
  const response = await fetch(`${backendUrl}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: 5 })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Query failed");
  }

  return response.json();
}

export async function ingestGithub(repoUrl: string, maxFiles: number): Promise<void> {
  const response = await fetch(`${backendUrl}/api/ingest/github`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl, max_files: maxFiles })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Ingestion failed");
  }
}

export async function sendQueryFeedback(queryId: number, feedback: -1 | 0 | 1): Promise<void> {
  const response = await fetch(`${backendUrl}/api/queries/${queryId}/feedback`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Feedback failed");
  }
}
