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
