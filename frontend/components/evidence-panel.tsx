"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { ExternalLink, X } from "lucide-react";
import { useRef } from "react";
import type { ReactNode } from "react";
import type { Evidence } from "@/lib/api";

type Variant = "bench" | "dialog";

function resolveEvidence(evidence: Evidence[], selectedId: string | null) {
  return selectedId === null
    ? evidence[0] ?? null
    : evidence.find((record) => record.citation_id === selectedId) ?? null;
}

function EvidenceContent({
  evidence,
  selectedId,
  variant
}: {
  evidence: Evidence[];
  selectedId: string | null;
  variant: Variant;
}) {
  const selected = resolveEvidence(evidence, selectedId);
  const citationLabel = selected?.citation_id ?? selectedId ?? "fonte";

  const Title = variant === "dialog" ? Dialog.Title : "h2";
  const Description = variant === "dialog" ? Dialog.Description : "p";

  if (!selected) {
    return (
      <div className="p-5">
        <Title className="font-serif text-lg font-semibold text-ink">Evidência indisponível</Title>
        <Description className="mt-2 text-sm leading-6 text-ink-soft">
          Nenhum trecho de fonte recuperado está disponível para esta citação.
        </Description>
        {variant === "dialog" ? (
          <Dialog.Close className="mt-4 rounded-md border border-line px-3 py-2 text-sm font-medium text-ink outline-none hover:bg-paper focus-visible:ring-4 focus-visible:ring-accent/20">
            Fechar
          </Dialog.Close>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b border-line px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">
              Inspeção da fonte
            </p>
            <Title className="mt-2 font-serif text-lg font-semibold leading-6 text-ink">
              Evidência para citação {citationLabel}
            </Title>
            <Description className="mt-1 text-sm leading-6 text-ink-soft">
              Trecho exato usado para sustentar a frase da resposta.
            </Description>
          </div>
          {variant === "dialog" ? (
            <Dialog.Close className="rounded-md p-2 text-ink-soft outline-none hover:bg-paper focus-visible:ring-4 focus-visible:ring-accent/20">
              <X size={18} aria-hidden="true" />
              <span className="sr-only">Fechar painel de evidência</span>
            </Dialog.Close>
          ) : null}
        </div>
      </header>

      <div
        role="region"
        aria-label="Detalhes da evidência"
        className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
      >
        <dl className="grid gap-3 rounded-md border border-line bg-paper p-4 text-sm">
          <Metadata label="Caminho">{selected.repository_path}</Metadata>
          {selected.section ? <Metadata label="Seção">{selected.section}</Metadata> : null}
          <Metadata label="Commit">{selected.commit_sha}</Metadata>
        </dl>

        <section className="mt-5" aria-label="Trecho original">
          <h3 className="text-sm font-semibold text-ink">Trecho original</h3>
          <p className="mt-3 whitespace-pre-wrap rounded-md border border-line bg-white p-4 font-mono text-[13px] leading-6 text-ink">
            {highlightSupportedText(selected.excerpt, selected.supported_text)}
          </p>
        </section>

        <a
          href={selected.source_url}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink outline-none hover:border-accent/50 hover:text-accent focus-visible:ring-4 focus-visible:ring-accent/20"
        >
          Abrir fonte fixada no commit
          <ExternalLink size={15} aria-hidden="true" />
        </a>
      </div>
    </div>
  );
}

export function EvidenceBench({
  evidence,
  selectedId
}: {
  evidence: Evidence[];
  selectedId: string | null;
}) {
  return (
    <section
      aria-label="Evidência da resposta"
      className="flex min-h-0 flex-1 flex-col bg-bench"
    >
      <EvidenceContent evidence={evidence} selectedId={selectedId} variant="bench" />
    </section>
  );
}

type EvidencePanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  evidence: Evidence[];
  selectedId: string | null;
};

export function EvidencePanel({ open, onOpenChange, evidence, selectedId }: EvidencePanelProps) {
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="evidence-dialog__overlay" />
        <Dialog.Content
          className="evidence-dialog__content"
          onOpenAutoFocus={() => {
            restoreFocusRef.current =
              document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (restoreFocusRef.current?.isConnected) {
              restoreFocusRef.current.focus();
            }
          }}
        >
          <EvidenceContent evidence={evidence} selectedId={selectedId} variant="dialog" />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Metadata({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[76px_1fr] sm:gap-3">
      <dt className="text-xs font-medium uppercase tracking-[0.14em] text-ink-soft">{label}</dt>
      <dd className="min-w-0 break-words font-medium text-ink">{children}</dd>
    </div>
  );
}

function highlightSupportedText(excerpt: string, supportedText: string | null): ReactNode {
  if (!supportedText) {
    return excerpt;
  }

  const start = excerpt.indexOf(supportedText);
  if (start === -1) {
    return excerpt;
  }

  const end = start + supportedText.length;

  return (
    <>
      {excerpt.slice(0, start)}
      <mark className="rounded-sm bg-amber-100 px-1 py-0.5 text-ink ring-1 ring-amber-300">
        {supportedText}
      </mark>
      {excerpt.slice(end)}
    </>
  );
}
