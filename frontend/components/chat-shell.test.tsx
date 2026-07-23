import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import RootLayout from "../app/layout";
import type { Evidence, PublicQueryResponse, QueryFeedbackResponse, ReadinessResponse } from "@/lib/api";
import { askDocs, checkReadiness, sendQueryFeedback } from "@/lib/api";
import { ChatShell } from "./chat-shell";

vi.mock("@/lib/api", () => ({
  askDocs: vi.fn(),
  checkReadiness: vi.fn(),
  sendQueryFeedback: vi.fn()
}));

const askDocsMock = vi.mocked(askDocs);
const checkReadinessMock = vi.mocked(checkReadiness);
const sendQueryFeedbackMock = vi.mocked(sendQueryFeedback);

const readyResponse: ReadinessResponse = {
  status: "ready",
  database: "ok",
  pgvector: "ok"
};

const wakingResponse: ReadinessResponse = {
  status: "not_ready",
  database: "ok",
  pgvector: "unknown"
};

const evidenceRecords: Evidence[] = [
  {
    citation_id: "c1",
    supported_text: "Execute uvicorn app.main:app --reload.",
    excerpt:
      "Para desenvolvimento local, execute uvicorn app.main:app --reload antes de abrir a interface web.",
    title: "Desenvolvimento local",
    repository_path: "docs/development/local.md",
    section: "Executar a API",
    commit_sha: "9f5d4e3a2b1c",
    source_url:
      "https://github.com/example/rag-docs-pipeline/blob/9f5d4e3a2b1c/docs/development/local.md#L18-L24",
    vector_score: 0.83,
    text_score: 0.71,
    fused_score: 0.89
  },
  {
    citation_id: "c2",
    supported_text: "Instale as dependencias do frontend com npm --prefix frontend install.",
    excerpt:
      "Instale as dependencias do frontend com npm --prefix frontend install e rode as verificacoes antes do deploy.",
    title: "Frontend setup",
    repository_path: "frontend/README.md",
    section: "Instalacao",
    commit_sha: "abc123def456",
    source_url: "https://github.com/example/rag-docs-pipeline/blob/abc123def456/frontend/README.md#L7",
    vector_score: 0.61,
    text_score: 0.58,
    fused_score: 0.64
  }
];

function answeredResponse(): PublicQueryResponse {
  return {
    event_id: "550e8400-e29b-41d4-a716-446655440000",
    state: "answered",
    answered: true,
    insufficient_evidence: false,
    answer: {
      sentences: [
        { text: "Execute uvicorn app.main:app --reload.", citation_id: "c1" },
        {
          text: "Instale as dependencias do frontend com npm --prefix frontend install.",
          citation_id: "c2"
        }
      ]
    },
    evidence: evidenceRecords,
    metrics: {
      latency_ms: 34,
      retrieved_chunk_count: 3,
      top_fused_score: 0.89,
      score_gap: 0.25
    }
  };
}

function duplicateCitationResponse(): PublicQueryResponse {
  return {
    ...answeredResponse(),
    answer: {
      sentences: [
        { text: "Execute uvicorn app.main:app --reload.", citation_id: "c1" },
        { text: "A API recarrega automaticamente durante o desenvolvimento.", citation_id: "c1" }
      ]
    }
  };
}

function insufficientResponse(): PublicQueryResponse {
  return {
    event_id: "550e8400-e29b-41d4-a716-446655440001",
    state: "insufficient_evidence",
    answered: false,
    insufficient_evidence: true,
    answer: null,
    evidence: [evidenceRecords[0]],
    metrics: {
      latency_ms: 19,
      retrieved_chunk_count: 1,
      top_fused_score: 0.31,
      score_gap: null
    }
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

async function submitQuestion(question = "Como executo localmente?") {
  const user = userEvent.setup();
  const input = screen.getByLabelText("Pergunta para a documentação");

  await waitFor(() => expect(input).toBeEnabled());
  await user.clear(input);
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Enviar pergunta" }));

  return user;
}

describe("ChatShell", () => {
  beforeEach(() => {
    askDocsMock.mockReset();
    checkReadinessMock.mockReset();
    sendQueryFeedbackMock.mockReset();
    checkReadinessMock.mockResolvedValue(readyResponse);
    sendQueryFeedbackMock.mockResolvedValue({
      event_id: "550e8400-e29b-41d4-a716-446655440000",
      feedback: 1
    } satisfies QueryFeedbackResponse);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  test("uses pt-BR as the root document language", () => {
    const root = RootLayout({ children: <main /> });

    expect(root.props.lang).toBe("pt-BR");
  });

  test("keeps the public surface free of admin and history controls while readiness disables the composer", async () => {
    const readiness = deferred<ReadinessResponse>();
    checkReadinessMock.mockReturnValueOnce(readiness.promise);

    render(<ChatShell />);

    expect(screen.getByLabelText("Pergunta para a documentação")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enviar pergunta" })).toBeDisabled();
    expect(screen.queryByText(/hist[oó]rico de consultas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/repository url|repo url|admin secret|max files/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ingest[aã]o|source management|analytics/i)).not.toBeInTheDocument();

    await act(async () => {
      readiness.resolve(readyResponse);
    });

    await waitFor(() => expect(screen.getByLabelText("Pergunta para a documentação")).toBeEnabled());
  });

  test("mirrors the backend question length limit in the public composer", async () => {
    render(<ChatShell />);

    const input = screen.getByLabelText("Pergunta para a documentação");

    await waitFor(() => expect(input).toBeEnabled());
    expect(input).toHaveAttribute("maxLength", "1000");
  });

  test("bounds cold-start readiness polling and exposes a retry path", async () => {
    vi.useFakeTimers();
    checkReadinessMock.mockResolvedValue(wakingResponse);

    render(<ChatShell />);

    await act(async () => {});
    expect(checkReadinessMock).toHaveBeenCalledTimes(1);

    for (const delay of [750, 1500, 3000]) {
      await act(async () => {
        vi.advanceTimersByTime(delay);
      });
    }

    const retry = screen.getByRole("button", { name: "Tentar novamente" });

    expect(checkReadinessMock).toHaveBeenCalledTimes(4);
    expect(screen.getByLabelText("Pergunta para a documentação")).toBeDisabled();

    checkReadinessMock.mockResolvedValueOnce(readyResponse);
    fireEvent.click(retry);

    await act(async () => {});
    expect(screen.getByLabelText("Pergunta para a documentação")).toBeEnabled();
  });

  test("renders every answer sentence with an inline citation button that opens the matching evidence", async () => {
    askDocsMock.mockResolvedValueOnce(answeredResponse());
    render(<ChatShell />);

    const user = await submitQuestion();
    const firstSentence = await screen.findByText("Execute uvicorn app.main:app --reload.");
    const secondSentence = screen.getByText(
      "Instale as dependencias do frontend com npm --prefix frontend install."
    );

    expect(within(firstSentence.closest("p") as HTMLElement).getByRole("button", {
      name: "Inspecionar evidência c1"
    })).toBeVisible();
    expect(within(secondSentence.closest("p") as HTMLElement).getByRole("button", {
      name: "Inspecionar evidência c2"
    })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Abrir fonte fixada no commit" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Inspecionar evidência c2" }));

    const dialog = await screen.findByRole("dialog", { name: "Evidência para citação c2" });
    expect(within(dialog).getByText("Inspeção da fonte")).toBeVisible();
    expect(
      within(dialog).getByText("Trecho exato usado para sustentar a frase da resposta.")
    ).toBeVisible();
    expect(within(dialog).getByRole("link", { name: "Abrir fonte fixada no commit" })).toBeVisible();
    expect(within(dialog).getByText("frontend/README.md")).toBeVisible();
    expect(within(dialog).queryByText("docs/development/local.md")).not.toBeInTheDocument();
  });

  test("keeps sentence keys stable when multiple answer sentences cite the same evidence", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      askDocsMock.mockResolvedValueOnce(duplicateCitationResponse());
      render(<ChatShell />);

      await submitQuestion();
      await screen.findByText("A API recarrega automaticamente durante o desenvolvimento.");

      const duplicateKeyMessages = consoleError.mock.calls
        .flat()
        .filter((message) => String(message).includes("Encountered two children with the same key"));

      expect(duplicateKeyMessages).toHaveLength(0);
    } finally {
      consoleError.mockRestore();
    }
  });

  test("opens the evidence panel automatically when evidence is insufficient and keeps the refusal visible", async () => {
    askDocsMock.mockResolvedValueOnce(insufficientResponse());
    render(<ChatShell />);

    await submitQuestion("Existe suporte a billing?");

    expect(
      await screen.findByText("Não encontrei evidências suficientes na documentação indexada para responder com segurança.")
    ).toBeVisible();
    expect(await screen.findByRole("dialog", { name: "Evidência para citação c1" })).toBeVisible();
  });

  test("rolls back optimistic UUID feedback when the public feedback request fails", async () => {
    const feedback = deferred<QueryFeedbackResponse>();
    sendQueryFeedbackMock.mockReturnValueOnce(feedback.promise);
    askDocsMock.mockResolvedValueOnce(answeredResponse());
    render(<ChatShell />);

    const user = await submitQuestion();
    const helpful = await screen.findByRole("button", { name: "Marcar resposta como útil" });

    await user.click(helpful);

    expect(sendQueryFeedbackMock).toHaveBeenCalledWith("550e8400-e29b-41d4-a716-446655440000", 1);
    expect(helpful).toHaveAttribute("aria-pressed", "true");

    await act(async () => {
      feedback.reject(new Error("Feedback indisponível"));
    });

    await waitFor(() => expect(helpful).toHaveAttribute("aria-pressed", "false"));
    expect(screen.getByText("Feedback indisponível")).toBeVisible();
  });
});
