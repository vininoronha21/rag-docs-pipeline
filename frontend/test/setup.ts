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
