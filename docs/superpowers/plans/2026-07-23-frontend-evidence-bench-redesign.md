# Frontend Evidence Bench Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the public chat around a persistent "evidence bench" (proof always visible beside the answer on desktop, bottom sheet on mobile) with an Inter-body / serif-headings editorial identity, and fold in the confirmed frontend fixes from the validation review.

**Architecture:** `chat-shell.tsx` owns query/readiness/feedback/selected-citation state and a two-pane layout. The evidence surface is split into a presentational `EvidenceContent` reused by two wrappers: an inline persistent bench (desktop) and the existing Radix `Dialog` sheet (mobile). A JS `useMediaQuery` hook (not CSS) decides which wrapper renders, so behavior is deterministic and testable in jsdom.

**Tech Stack:** Next.js 16, React 18, TypeScript, Tailwind 3, Radix Dialog, lucide-react, `next/font/google`, Vitest + Testing Library (jsdom).

## Global Constraints

- Scope is `frontend/` only. No backend changes. Backend CI failure is out of scope.
- No new runtime dependencies beyond fonts loaded via `next/font/google` (self-hosted at build; no runtime network).
- No dark mode. `color-scheme: light` stays.
- Root document language stays `pt-BR` (`app/layout.tsx`).
- Public composer `maxLength` stays `1000` (mirrors backend).
- Admin Bearer secret stays in memory only — do not touch `admin-shell.tsx` state handling; identity tokens only.
- Public question label text stays exactly `Pergunta para a documentação` (tests depend on it).
- Send button accessible name stays exactly `Enviar pergunta`.
- Refusal copy stays exactly: `Não encontrei evidências suficientes na documentação indexada para responder com segurança.`
- Citation chip accessible name stays exactly `Inspecionar evidência <citation_id>`.
- Source link accessible name stays exactly `Abrir fonte fixada no commit`.
- All new text/background color pairs must meet WCAG AA contrast.
- Motion gated behind `@media (prefers-reduced-motion: no-preference)`.
- Every task ends green on: `npm run typecheck`, `npm run test:run`, and `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build`.

---

### Task 1: Design tokens and fonts

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/globals.css:5-17`

**Interfaces:**
- Consumes: nothing.
- Produces: Tailwind color tokens `paper`, `bench`, `ink`, `ink-soft`, `line`, `accent`; `fontFamily` tokens `sans`, `serif`, `mono`; CSS variables `--font-sans` (Inter) and `--font-serif` (Fraunces) attached to `<body>`.

- [ ] **Step 1: Add fonts and body variables in `app/layout.tsx`**

Replace the file with:

```tsx
import type { Metadata } from "next";
import { Inter, Fraunces } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap"
});

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-serif",
  display: "swap"
});

export const metadata: Metadata = {
  title: "RAG Docs Pipeline",
  description: "Semantic search and cited answers for fragmented documentation."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${inter.variable} ${fraunces.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: Extend Tailwind tokens in `tailwind.config.ts`**

Replace the `theme.extend` block with:

```ts
    extend: {
      colors: {
        ink: "#1f1b16",
        "ink-soft": "#57534e",
        paper: "#f7f4ee",
        bench: "#efeae0",
        surface: "#f7f4ee",
        line: "#ddd6c9",
        accent: "#0b5f57"
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"]
      }
    }
```

(Keep `surface` as an alias of paper so any existing `bg-surface` usage stays valid.)

- [ ] **Step 3: Warm the body background in `globals.css`**

Change the `body` rule (lines 13-17) to:

```css
body {
  margin: 0;
  background: #f7f4ee;
  color: #1f1b16;
  font-family: var(--font-sans), system-ui, sans-serif;
}
```

Leave the `.evidence-dialog__*` rules unchanged.

- [ ] **Step 4: Verify typecheck, tests, and build pass**

Run: `npm run typecheck && npm run test:run`
Expected: typecheck clean; 23 tests pass (the `RootLayout` pt-BR test still passes — `root.props.lang` is `"pt-BR"`).

Run: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build`
Expected: build succeeds; fonts fetched by `next/font/google` at build time.

- [ ] **Step 5: Commit**

```bash
git add frontend/tailwind.config.ts frontend/app/layout.tsx frontend/app/globals.css
git commit -m "feat(frontend): editorial paper tokens + Inter/Fraunces fonts"
```

---

### Task 2: `useMediaQuery` hook + matchMedia test mock

**Files:**
- Create: `frontend/lib/use-media-query.ts`
- Create: `frontend/lib/use-media-query.test.ts`
- Modify: `frontend/test/setup.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `export function useMediaQuery(query: string): boolean` — returns whether the media query currently matches; subscribes to changes. Used by later tasks with the exact query string `(min-width: 1024px)` to mean "desktop".

- [ ] **Step 1: Add a matchMedia mock to `test/setup.ts`**

jsdom does not implement `window.matchMedia`. Add a controllable mock (defaults to matching — i.e. desktop — so existing/default tests run in the desktop bench layout):

```ts
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom has no matchMedia. Default: every query matches (desktop layout).
// Tests override window.matchMedia per-case to simulate mobile.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn()
  }));
}
```

- [ ] **Step 2: Write the failing hook test**

Create `frontend/lib/use-media-query.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useMediaQuery } from "./use-media-query";

type Listener = (event: { matches: boolean }) => void;

function mockMatchMedia(initialMatches: boolean) {
  let listener: Listener | null = null;
  const mql = {
    matches: initialMatches,
    media: "(min-width: 1024px)",
    onchange: null,
    addEventListener: (_type: string, cb: Listener) => {
      listener = cb;
    },
    removeEventListener: () => {
      listener = null;
    },
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false
  };
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
  return {
    emit(next: boolean) {
      mql.matches = next;
      listener?.({ matches: next });
    }
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMediaQuery", () => {
  test("returns the initial match state", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(true);
  });

  test("updates when the media query changes", () => {
    const controller = mockMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);

    act(() => controller.emit(true));
    expect(result.current).toBe(true);
  });
});
```

- [ ] **Step 2b: Run the test to verify it fails**

Run: `npm run test:run -- use-media-query`
Expected: FAIL — `useMediaQuery` is not defined / module not found.

- [ ] **Step 3: Implement the hook**

Create `frontend/lib/use-media-query.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
```

Note: initial state is `false` and syncs in `useEffect` to avoid SSR/client hydration mismatch (server has no `matchMedia`). Consumers must treat the first client paint as "not matched" and upgrade after mount.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm run test:run -- use-media-query`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/use-media-query.ts frontend/lib/use-media-query.test.ts frontend/test/setup.ts
git commit -m "feat(frontend): add useMediaQuery hook + matchMedia test mock"
```

---

### Task 3: Extract `EvidenceContent`; add inline vs dialog variants

**Files:**
- Modify: `frontend/components/evidence-panel.tsx`
- Modify: `frontend/components/evidence-panel.test.tsx`

**Interfaces:**
- Consumes: `Evidence` from `@/lib/api`.
- Produces:
  - `EvidenceContent({ evidence, selectedId, variant }: { evidence: Evidence[]; selectedId: string | null; variant: "bench" | "dialog" })` — renders header, metadata, highlighted excerpt, source link, or the empty state. When `variant === "bench"` it renders plain headings; when `variant === "dialog"` it renders `Dialog.Title`/`Dialog.Description`. Selection resolution: `selectedId === null` → `evidence[0] ?? null`; otherwise `evidence.find(e => e.citation_id === selectedId) ?? null`.
  - `EvidencePanel({ open, onOpenChange, evidence, selectedId })` — unchanged public signature; internally wraps `EvidenceContent variant="dialog"` in the Radix `Dialog` (mobile sheet). `highlightSupportedText` stays as-is.
  - New export `EvidenceBench({ evidence, selectedId }: { evidence: Evidence[]; selectedId: string | null })` — renders `EvidenceContent variant="bench"` inside a `<section aria-label="Evidência da resposta">`.

- [ ] **Step 1: Write the failing test for the bench variant**

Add to `frontend/components/evidence-panel.test.tsx` (keep existing tests):

```tsx
import { EvidenceBench } from "./evidence-panel";

// ...inside the existing describe or a new one:
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
```

Reuse the existing `sampleEvidence` fixture in that test file. If the file has no shared fixture named `sampleEvidence`, add one at module top mirroring the two records used elsewhere (citation ids `c1` for `docs/development/local.md` and `c2` for `frontend/README.md`, each with `excerpt`, `supported_text`, `commit_sha`, `source_url`).

- [ ] **Step 2: Run to verify it fails**

Run: `npm run test:run -- evidence-panel`
Expected: FAIL — `EvidenceBench` is not exported.

- [ ] **Step 3: Refactor `evidence-panel.tsx`**

Replace the file body so `EvidenceContent` holds the shared markup and both wrappers reuse it:

```tsx
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
```

Note: the existing `evidence-panel` dialog tests assert `getByRole("dialog", { name: "Evidência para citação c2" })`. Radix names the dialog from `Dialog.Title`, which `EvidenceContent variant="dialog"` still renders — so those existing tests keep passing.

- [ ] **Step 4: Run to verify it passes**

Run: `npm run test:run -- evidence-panel`
Expected: PASS (existing dialog tests + 2 new bench tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/evidence-panel.tsx frontend/components/evidence-panel.test.tsx
git commit -m "feat(frontend): split EvidenceContent into bench + dialog variants"
```

---

### Task 4: Refusal gating fix + answered-empty edge

**Files:**
- Modify: `frontend/components/chat-shell.tsx`
- Modify: `frontend/components/chat-shell.test.tsx`

**Interfaces:**
- Consumes: `PublicQueryResponse` from `@/lib/api`.
- Produces: an `isRefusal` derivation inside `ChatShell`: `const isRefusal = response !== null && (response.insufficient_evidence || (response.answer?.sentences.length ?? 0) === 0);`. Refusal copy AND the "Evidência insuficiente" badge render iff `isRefusal`. Feedback thumbs render iff `response && !isRefusal`.

- [ ] **Step 1: Write the failing tests**

Add to `chat-shell.test.tsx`. First a fixture for an answered-but-empty edge (place beside the other fixture builders):

```tsx
function answeredButEmptyResponse(): PublicQueryResponse {
  return {
    event_id: "550e8400-e29b-41d4-a716-446655440002",
    state: "answered",
    answered: true,
    insufficient_evidence: false,
    answer: { sentences: [] },
    evidence: [evidenceRecords[0]],
    metrics: { latency_ms: 12, retrieved_chunk_count: 1, top_fused_score: 0.4, score_gap: null }
  };
}
```

Then the tests:

```tsx
test("shows the refusal badge and copy only for insufficient evidence, with no feedback controls", async () => {
  askDocsMock.mockResolvedValueOnce(insufficientResponse());
  render(<ChatShell />);

  await submitQuestion("Existe suporte a billing?");

  expect(
    await screen.findByText(
      "Não encontrei evidências suficientes na documentação indexada para responder com segurança."
    )
  ).toBeVisible();
  expect(screen.getByText("Evidência insuficiente")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Marcar resposta como útil" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Marcar resposta como não útil" })).not.toBeInTheDocument();
});

test("treats an answered response with no sentences as a refusal", async () => {
  askDocsMock.mockResolvedValueOnce(answeredButEmptyResponse());
  render(<ChatShell />);

  await submitQuestion();

  expect(
    await screen.findByText(
      "Não encontrei evidências suficientes na documentação indexada para responder com segurança."
    )
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Marcar resposta como útil" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm run test:run -- chat-shell`
Expected: FAIL — feedback thumbs currently render for any `response`; the empty-answered case currently shows refusal copy but still renders thumbs.

- [ ] **Step 3: Implement gating in `chat-shell.tsx`**

After `const sentences = response?.answer?.sentences ?? [];` add:

```tsx
  const isRefusal = response !== null && (response.insufficient_evidence || sentences.length === 0);
```

In the response `<article>`: gate the badge on `isRefusal` (replace the `response.insufficient_evidence ?` condition with `isRefusal ?`), render sentences when `!isRefusal` else the `refusalText` paragraph, and wrap the entire feedback `<div>` (the "Feedback" label + both thumb buttons) in `{response && !isRefusal ? ( ... ) : null}`.

- [ ] **Step 4: Run to verify they pass**

Run: `npm run test:run -- chat-shell`
Expected: PASS, including the existing "keeps the refusal visible" test.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/chat-shell.tsx frontend/components/chat-shell.test.tsx
git commit -m "fix(frontend): gate refusal copy/badge/feedback on evidence state"
```

---

### Task 5: Two-pane bench layout + persistent evidence wiring

**Files:**
- Modify: `frontend/components/chat-shell.tsx`
- Modify: `frontend/components/chat-shell.test.tsx`

**Interfaces:**
- Consumes: `EvidenceBench`, `EvidencePanel` from `./evidence-panel`; `useMediaQuery` from `@/lib/use-media-query`.
- Produces: desktop (`useMediaQuery("(min-width: 1024px)") === true`) renders the persistent `EvidenceBench` in the right pane and never opens the dialog; mobile renders `EvidencePanel` (sheet) on chip click. Selected citation defaults to the first evidence `citation_id` when an answered response arrives. Chips call a single `selectEvidence(citationId)` that sets `selectedEvidenceId` and, on mobile only, opens the sheet.

- [ ] **Step 1: Write the failing tests**

Add a mobile helper at the top of `chat-shell.test.tsx` (below imports):

```tsx
function setViewport(isDesktop: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: isDesktop,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn()
  })) as unknown as typeof window.matchMedia;
}
```

Reset it in `beforeEach` by calling `setViewport(true)` (desktop default). Then:

```tsx
test("desktop shows the persistent evidence bench and switches it on citation click without a dialog", async () => {
  setViewport(true);
  askDocsMock.mockResolvedValueOnce(answeredResponse());
  render(<ChatShell />);

  const user = await submitQuestion();

  const bench = await screen.findByLabelText("Evidência da resposta");
  // defaults to citation c1
  expect(within(bench).getByText("docs/development/local.md")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Inspecionar evidência c2" }));

  expect(within(bench).getByText("frontend/README.md")).toBeVisible();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("mobile opens the evidence sheet on citation click", async () => {
  setViewport(false);
  askDocsMock.mockResolvedValueOnce(answeredResponse());
  render(<ChatShell />);

  const user = await submitQuestion();
  await user.click(await screen.findByRole("button", { name: "Inspecionar evidência c2" }));

  expect(await screen.findByRole("dialog", { name: "Evidência para citação c2" })).toBeVisible();
});
```

Update the existing test `renders every answer sentence ...` — it currently clicks a chip and asserts a `dialog`. Under the desktop default it must instead assert the bench updates. Change its final block (after the two `toBeVisible` chip assertions) to:

```tsx
  await user.click(screen.getByRole("button", { name: "Inspecionar evidência c2" }));
  const bench = screen.getByLabelText("Evidência da resposta");
  expect(within(bench).getByText("frontend/README.md")).toBeVisible();
  expect(within(bench).queryByText("docs/development/local.md")).not.toBeInTheDocument();
```

Update the existing test `opens the evidence panel automatically when evidence is insufficient` — on desktop the bench shows the evidence inline (no dialog). Change its dialog assertion to:

```tsx
  const bench = await screen.findByLabelText("Evidência da resposta");
  expect(within(bench).getByText("docs/development/local.md")).toBeVisible();
```

- [ ] **Step 2: Run to verify the new/updated tests fail**

Run: `npm run test:run -- chat-shell`
Expected: FAIL — no `EvidenceBench` rendered yet; layout still single-column with modal.

- [ ] **Step 3: Rewrite `ChatShell` layout and wiring**

Apply these edits to `chat-shell.tsx`:

1. Add imports:
```tsx
import { EvidenceBench, EvidencePanel } from "@/components/evidence-panel";
import { useMediaQuery } from "@/lib/use-media-query";
```
(remove the old `EvidencePanel`-only import line).

2. Inside the component, after the state hooks add:
```tsx
  const isDesktop = useMediaQuery("(min-width: 1024px)");
```

3. Replace `openEvidencePanel` with a unified selector:
```tsx
  function selectEvidence(evidence: Evidence[], citationId: string | null) {
    setPanelEvidence(evidence);
    setSelectedEvidenceId(citationId);
    if (!isDesktop) {
      setEvidencePanelOpen(true);
    }
  }
```

4. In `handleQuestion`, after `setResponse(nextResponse);` set the default selection and only auto-open the sheet on mobile refusal:
```tsx
      const defaultCitation =
        nextResponse.answer?.sentences[0]?.citation_id ??
        nextResponse.evidence[0]?.citation_id ??
        null;
      setPanelEvidence(nextResponse.evidence);
      setSelectedEvidenceId(defaultCitation);

      if (nextResponse.insufficient_evidence && !isDesktop) {
        setEvidencePanelOpen(true);
      }
```
(remove the old `if (nextResponse.insufficient_evidence) { openEvidencePanel(...) }` block).

5. Chip `onClick` becomes `() => selectEvidence(response.evidence, sentence.citation_id)`.

6. Replace the outer layout. The new top-level structure: a top bar, then a two-pane grid on desktop / single column on mobile. Replace the `return (...)` markup's root `<main>` down to the closing `</main>` with:

```tsx
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
```

7. Add the feedback subcomponent and the error ref. Near the top of the component add:
```tsx
  const errorRef = useRef<HTMLDivElement | null>(null);
```
and add `useRef` to the `react` import. Add at the bottom of the file:

```tsx
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
```

Ensure `QueryFeedback` is imported in the `import type { ... } from "@/lib/api"` line (it already imports `QueryFeedback`).

Note on the `Evidence` type: `selectEvidence` takes `Evidence[]`; add `Evidence` to the existing `import type` from `@/lib/api` if not already present (it is).

- [ ] **Step 4: Run to verify tests pass**

Run: `npm run test:run -- chat-shell evidence-panel`
Expected: PASS — desktop bench switching, mobile sheet, refusal-inline-on-desktop, and all prior tests.

- [ ] **Step 5: Full suite + build**

Run: `npm run typecheck && npm run test:run`
Expected: all tests pass (23 baseline minus the reworked dialog assertions, plus the new ones).

Run: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/chat-shell.tsx frontend/components/chat-shell.test.tsx
git commit -m "feat(frontend): two-pane evidence bench layout + mobile sheet"
```

---

### Task 6: Error placement/focus + feedback confirmation regression tests

**Files:**
- Modify: `frontend/components/chat-shell.test.tsx`

**Interfaces:**
- Consumes: the `errorRef`/inline-error markup and `FeedbackControls` from Task 5.
- Produces: no source change — this task locks the fixed behaviors with tests. If a test fails, fix `chat-shell.tsx` minimally to satisfy it (focus-move on error, no re-fire on repeat thumb).

- [ ] **Step 1: Write the tests**

```tsx
test("moves focus to the inline error when a query fails", async () => {
  askDocsMock.mockRejectedValueOnce(new Error("Falha na consulta"));
  render(<ChatShell />);

  await submitQuestion();

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Falha na consulta");
  await waitFor(() => expect(alert).toHaveFocus());
});

test("does not re-send feedback when the already-selected thumb is clicked again", async () => {
  askDocsMock.mockResolvedValueOnce(answeredResponse());
  render(<ChatShell />);

  const user = await submitQuestion();
  const helpful = await screen.findByRole("button", { name: "Marcar resposta como útil" });

  await user.click(helpful);
  expect(sendQueryFeedbackMock).toHaveBeenCalledTimes(1);

  await user.click(helpful);
  expect(sendQueryFeedbackMock).toHaveBeenCalledTimes(1);
  expect(await screen.findByText("Obrigado pelo retorno")).toBeVisible();
});
```

- [ ] **Step 2: Run to verify**

Run: `npm run test:run -- chat-shell`
Expected: the re-fire and confirmation tests PASS (behavior built in Task 5). The focus test may FAIL if focus is not moved on error.

- [ ] **Step 3: If the focus test fails, move focus on error**

In `handleQuestion`'s `catch`, after `setError(...)`, and in `handleFeedback`'s `catch` after `setError(...)`, focus the alert on the next tick:

```tsx
      setError(err instanceof Error ? err.message : "Não foi possível consultar a documentação.");
      requestAnimationFrame(() => errorRef.current?.focus());
```

(Use the same `requestAnimationFrame(() => errorRef.current?.focus());` line in the feedback catch, adjusting the fallback message string that is already there.)

- [ ] **Step 4: Run to verify all pass**

Run: `npm run test:run -- chat-shell`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/chat-shell.tsx frontend/components/chat-shell.test.tsx
git commit -m "fix(frontend): focus inline error; confirm feedback and block re-send"
```

---

### Task 7: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Typecheck**

Run: `npm run typecheck`
Expected: clean.

- [ ] **Step 2: Full test suite**

Run: `npm run test:run`
Expected: all suites pass (`api`, `evidence-panel`, `chat-shell`, `admin-shell`, `use-media-query`).

- [ ] **Step 3: Production build**

Run: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build`
Expected: build succeeds; three static routes (`/`, `/_not-found`, `/admin`).

- [ ] **Step 4: Manual smoke (document results, do not commit)**

Run: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run dev` and verify against a running backend (or note that a backend is required):
- Desktop ≥1024px: two panes; asking a question shows the answer left, bench right defaulting to `[1]`; clicking `[2]` swaps the bench, no dialog.
- Mobile <1024px (devtools responsive): single column; tapping a chip opens the bottom sheet; refusal auto-opens the sheet.
- Forced error: error appears above the composer and receives focus.
- Refusal: badge + refusal copy, no feedback thumbs.
- Keyboard: tab reaches chips, composer, send, feedback, and the source link; focus rings visible.

- [ ] **Step 5: Commit (only if any manual-fix was needed)**

```bash
git add -A
git commit -m "chore(frontend): finalize evidence bench redesign verification"
```

---

## Self-Review

**Spec coverage:**
- Layout two-pane desktop / mobile sheet → Task 5. ✓
- Persistent bench + default [1] + cross-fade → Task 5 (cross-fade is a CSS nicety; add `transition` classes on the bench container during Task 5 markup — noted; not test-gated). ✓
- Removed 340px sidebar / top-bar readiness / inline error → Task 5. ✓
- Identity: Inter body + serif headings + mono chips, paper/bench/ink-soft tokens, ≥44px feedback / ≥24px inline chips, reduced-motion → Tasks 1, 3, 5. ✓
- Fix: refusal gating + answered-empty edge → Task 4. ✓
- Fix: error placement + focus → Tasks 5, 6. ✓
- Fix: tap targets → Tasks 3 (source link min-h-11), 5 (feedback h-11 w-11, chips min 24px). ✓
- Fix: feedback confirmation + no re-fire → Tasks 5, 6. ✓
- Admin identity inheritance → automatic via token/font changes in Task 1 (no structural edit). ✓
- Testing/verification → Tasks 6, 7. ✓

**Placeholder scan:** No TBD/TODO. Cross-fade left as an untested visual detail is explicit, not a placeholder. Serif face is concretely `Fraunces`.

**Type consistency:** `selectEvidence(evidence: Evidence[], citationId: string | null)`, `EvidenceBench({ evidence, selectedId })`, `EvidencePanel` signature unchanged, `useMediaQuery(query: string): boolean`, `isRefusal: boolean`, `FeedbackControls({ feedback, onFeedback })` — consistent across tasks.
