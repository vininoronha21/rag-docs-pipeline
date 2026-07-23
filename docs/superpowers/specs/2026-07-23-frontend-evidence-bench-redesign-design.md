# Frontend Redesign — Evidence Bench

Date: 2026-07-23
Status: approved (design), pending implementation plan
Scope: `frontend/` only. Backend and backend CI failure are out of scope.

## Goal

Redesign the public chat UI around a persistent "evidence bench": the cited
proof is always visible next to the answer on desktop, making the
citation-first / commit-pinned story the visual hero. Replace the current
cold teal-slate sidebar layout with a warmer editorial/technical identity.
Fold in the confirmed frontend fixes from the validation review.

The admin shell inherits the new identity tokens and typography only; its
structure is not reworked.

## Non-goals

- No backend changes. The backend CI unit-test failure is tracked separately.
- No dark mode.
- No new dependencies beyond a web font loaded via `next/font`.
- No admin structural redesign.

## Current state (baseline)

- `app/page.tsx` → `components/chat-shell.tsx`: two-column grid
  `[340px_1fr]`. Left sidebar holds title + readiness + error alert. Right
  column is the conversation with a bottom composer.
- `components/evidence-panel.tsx`: Radix `Dialog` used as a modal / bottom
  sheet, opened on citation-chip click.
- Tokens (`tailwind.config.ts`): `ink #111827`, `surface #f8fafc`,
  `line #d7dee8`, `accent #0f766e`. No custom fonts; `color-scheme: light`.
- Tests: `chat-shell.test.tsx` (8), `evidence-panel.test.tsx` (4),
  `admin-shell.test.tsx` (5), `api.test.ts` (6). All green locally and in CI.

## Layout

### Desktop (lg and up)

Two-pane bench inside a max-width container, full viewport height:

- **Left pane — conversation.** Compact top bar (product name + inline
  readiness pill). Scrollable thread: submitted question bubble, loading
  state, extracted answer with inline citation chips. Composer pinned to the
  bottom of this pane. Inline error alert sits directly above the composer.
- **Right pane — evidence bench (persistent).** Shows the selected citation's
  proof: repository path, optional section, commit SHA chip, highlighted
  excerpt, and "abrir fonte fixada no commit" link. This is the same content
  the modal renders today, promoted to an always-visible panel.
  - Before any answer: shows a short "como funciona" explainer (extractive,
    citation-first, commit-pinned).
  - After an answered response: defaults to citation `[1]`.
  - Clicking a citation chip swaps the panel to that citation and applies a
    subtle cross-fade (respecting `prefers-reduced-motion`).
  - Insufficient-evidence response: panel shows the best-available evidence
    (current auto-open behavior), or an explicit empty state if none.

### Mobile (below lg)

- Single column: top bar, thread, composer, inline error above composer.
- Evidence uses a **bottom sheet** (reuse the existing Radix `Dialog` +
  `globals.css` sheet styles) triggered by a citation chip. The persistent
  right pane is not rendered at this breakpoint.

### Removed

- The 340px left sidebar. Title collapses into the top bar; readiness becomes
  an inline status pill; the error alert moves next to the composer.

## Visual identity

Editorial / technical:

- **Typography.** Serif display face for headings (question label, answer
  heading, evidence heading), loaded via `next/font` (Fraunces or Source
  Serif — pick one, self-hosted by `next/font`, no network dependency at
  runtime). Sans body (Inter or system stack). Monospace for citation chips,
  commit SHA, and the excerpt block. Expose as CSS variables consumed by
  Tailwind `fontFamily` tokens.
- **Color.** Warm paper surface replacing cold slate; a slightly darker
  "bench" tone for the evidence pane to separate proof from answer; deepen
  the accent teal for contrast on paper. New tokens: `paper`, `bench`,
  `ink-soft` (plus existing `ink`, `line`, `accent`). All text/background
  pairs must meet WCAG AA contrast.
- **Citation chips.** Monospace `[n]`, minimum 44x44px hit area, clear
  selected state kept in sync with the bench panel.
- **Motion.** Cross-fade the bench content on citation switch; gated behind
  `@media (prefers-reduced-motion: no-preference)`.

## Frontend fixes (from validation review)

1. **Refusal gating (Important).** Gate the refusal copy AND the "Evidência
   insuficiente" badge on `response.insufficient_evidence`, not on
   `sentences.length`. Handle the answered-but-empty-sentences edge
   explicitly (treat as refusal, no feedback thumbs).
2. **Error placement (Important).** Render query/feedback errors inline
   directly above the composer, and move focus to the alert on error so it is
   not stranded off-screen on mobile.
3. **Tap targets (Minor).** Citation chips and feedback buttons at least
   44x44px.
4. **Feedback affordance (Minor).** Show a "obrigado" confirmation after
   successful feedback; do not re-fire the PATCH when the already-selected
   thumb is clicked again. Event UUID stays out of the UI.

## Components and boundaries

- `chat-shell.tsx` — owns query/readiness/feedback state and the two-pane
  layout. Selected-citation state lifts here so the persistent bench and the
  chips share one source of truth (currently `selectedEvidenceId` already
  lives here).
- `evidence-panel.tsx` — refactored to render its body in two contexts:
  (a) inline as the persistent desktop bench, (b) inside the Radix `Dialog`
  sheet on mobile. Extract the inner content (header, metadata, excerpt,
  source link, empty state) into a presentational piece reused by both; the
  `Dialog` wrapper becomes mobile-only. `highlightSupportedText` unchanged.
- `admin-shell.tsx` — no structural change; picks up new font/color tokens.
- `tailwind.config.ts` — add `paper`, `bench`, `ink-soft` colors and
  `fontFamily` serif/sans/mono entries.
- `app/layout.tsx` — load the serif + sans fonts via `next/font`, attach the
  CSS variables to `<body>`.
- `globals.css` — update `body` background to paper; keep the existing sheet
  styles for the mobile evidence dialog.

## Data flow

Unchanged API contract (`lib/api.ts`). Answer arrives → sentences render with
chips → selecting a chip sets `selectedEvidenceId` → desktop bench reads it
directly; mobile opens the sheet with it. No new fetches, no new persistence.
Admin Bearer secret stays in memory only (unchanged, already verified).

## Error handling

- Query failure: inline alert above composer, focus moved to it, `role="alert"`.
- Feedback failure: same inline alert; optimistic state rolls back (existing
  behavior preserved).
- Insufficient evidence: refusal copy + badge gated on the state flag; bench
  shows best-available evidence or explicit empty state.
- Readiness blocked: inline "tentar novamente" in the top-bar status region.

## Testing

Extend existing suites (Testing Library, no snapshot churn on class names):

- Refusal path: `insufficient_evidence: true` → badge + refusal copy shown,
  no feedback thumbs. Answered-but-empty-sentences → treated as refusal.
- Error placement: rejected `askDocs` → alert rendered in the composer region
  (not a removed sidebar) and receives focus.
- Persistent bench (desktop): after an answered response, bench shows
  citation `[1]`; clicking `[2]` swaps bench content to `[2]`.
- Mobile sheet: citation chip opens the Radix dialog with the matching
  evidence (existing behavior retained at small breakpoint).
- Feedback confirmation: success shows "obrigado"; re-clicking the selected
  thumb does not issue a second PATCH.
- Regression: all 23 existing tests still pass; typecheck and
  `NEXT_PUBLIC_BACKEND_URL=... npm run build` succeed.

## Verification

- `npm run typecheck`
- `npm run test:run`
- `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build`
- Manual: desktop two-pane + citation switching; mobile single column + sheet;
  refusal state; forced error visibility/focus; keyboard nav across chips,
  composer, feedback, and source link.

## Risks

- Serif font choice affects perceived polish; validate contrast and weight on
  paper before committing.
- Splitting the evidence content for dual rendering must not regress the
  focus-restore behavior the mobile dialog currently guarantees.
- `highlightSupportedText` still silently no-ops on non-exact substrings
  (known minor from review); left as-is this pass.
