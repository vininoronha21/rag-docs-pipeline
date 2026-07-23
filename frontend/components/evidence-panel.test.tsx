import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { Evidence } from "@/lib/api";
import { EvidenceBench, EvidencePanel } from "./evidence-panel";

const evidenceRecords: Evidence[] = [
  {
    citation_id: "c1",
    supported_text: "run uvicorn app.main:app --reload",
    excerpt:
      "During local development, run uvicorn app.main:app --reload from the repository root before opening the docs UI.",
    title: "Local development",
    repository_path: "docs/development/local.md",
    section: "Run the API",
    commit_sha: "9f5d4e3a2b1c",
    source_url:
      "https://github.com/example/rag-docs-pipeline/blob/9f5d4e3a2b1c/docs/development/local.md#L18-L24",
    vector_score: 0.83,
    text_score: 0.71,
    fused_score: 0.89
  },
  {
    citation_id: "c2",
    supported_text: "install dependencies with npm --prefix frontend install",
    excerpt:
      "For the public client, install dependencies with npm --prefix frontend install and then run the frontend checks.",
    title: "Frontend setup",
    repository_path: "frontend/README.md",
    section: "Install",
    commit_sha: "abc123def456",
    source_url: "https://github.com/example/rag-docs-pipeline/blob/abc123def456/frontend/README.md#L7",
    vector_score: 0.61,
    text_score: 0.58,
    fused_score: 0.64
  }
];

// Alias for new bench tests (same data, different name used by the brief)
const sampleEvidence = evidenceRecords;

function EvidencePanelHarness() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Inspecionar evidência
      </button>
      <EvidencePanel open={open} onOpenChange={setOpen} evidence={evidenceRecords} selectedId="c2" />
    </>
  );
}

describe("EvidencePanel", () => {
  afterEach(() => {
    cleanup();
  });

  test("shows the selected source excerpt with path, section, commit, pinned link, and highlighted support", () => {
    const onOpenChange = vi.fn();

    render(
      <EvidencePanel
        open
        onOpenChange={onOpenChange}
        evidence={evidenceRecords}
        selectedId="c2"
      />
    );

    const dialog = screen.getByRole("dialog", { name: "Evidência para citação c2" });

    expect(within(dialog).getByText("Inspeção da fonte")).toBeVisible();
    expect(
      within(dialog).getByText("Trecho exato usado para sustentar a frase da resposta.")
    ).toBeVisible();
    expect(within(dialog).getByText("frontend/README.md")).toBeVisible();
    expect(within(dialog).getByText("Install")).toBeVisible();
    expect(within(dialog).getByText("abc123def456")).toBeVisible();
    expect(within(dialog).getByText(/For the public client/)).toBeVisible();
    expect(within(dialog).getByText("install dependencies with npm --prefix frontend install").tagName).toBe(
      "MARK"
    );

    const sourceLink = within(dialog).getByRole("link", { name: "Abrir fonte fixada no commit" });
    expect(sourceLink).toHaveAttribute(
      "href",
      "https://github.com/example/rag-docs-pipeline/blob/abc123def456/frontend/README.md#L7"
    );
    expect(sourceLink).toHaveAttribute("target", "_blank");
    expect(dialog).not.toHaveTextContent("0.64");
    expect(dialog).not.toHaveTextContent(/confidence/i);
  });

  test("shows the unavailable state when a requested citation id is missing", () => {
    const onOpenChange = vi.fn();

    render(
      <EvidencePanel
        open
        onOpenChange={onOpenChange}
        evidence={evidenceRecords}
        selectedId="missing-citation"
      />
    );

    const dialog = screen.getByRole("dialog", { name: "Evidência indisponível" });

    expect(
      within(dialog).getByText("Nenhum trecho de fonte recuperado está disponível para esta citação.")
    ).toBeVisible();
    expect(dialog).not.toHaveTextContent("docs/development/local.md");
    expect(dialog).not.toHaveTextContent("During local development");
  });

  test("bounds the evidence body as the scrollable region for long excerpts", () => {
    const onOpenChange = vi.fn();

    render(
      <EvidencePanel
        open
        onOpenChange={onOpenChange}
        evidence={evidenceRecords}
        selectedId="c2"
      />
    );

    const dialog = screen.getByRole("dialog", { name: "Evidência para citação c2" });
    const evidenceBody = within(dialog).getByRole("region", { name: "Detalhes da evidência" });

    expect(dialog).toHaveClass("evidence-dialog__content");
    expect(evidenceBody).toHaveClass("min-h-0", "flex-1", "overflow-y-auto");
  });

  test("closes on Escape and restores focus to the opener", async () => {
    const user = userEvent.setup();

    render(<EvidencePanelHarness />);

    const opener = screen.getByRole("button", { name: "Inspecionar evidência" });
    await user.click(opener);

    expect(screen.getByRole("dialog", { name: "Evidência para citação c2" })).toBeVisible();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Evidência para citação c2" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("EvidenceBench", () => {
  afterEach(() => {
    cleanup();
  });

  test("EvidenceBench renders the selected citation inline without a dialog", () => {
    render(<EvidenceBench evidence={sampleEvidence} selectedId="c2" />);

    expect(screen.getByLabelText("Evidência da resposta")).toBeInTheDocument();
    expect(screen.getByText("frontend/README.md")).toBeVisible();
    expect(screen.getByRole("link", { name: "Abrir fonte fixada no commit" })).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("EvidenceBench shows the empty state when no evidence resolves", () => {
    render(<EvidenceBench evidence={[]} selectedId={null} />);
    expect(screen.getByText("Evidência indisponível")).toBeVisible();
  });
});
