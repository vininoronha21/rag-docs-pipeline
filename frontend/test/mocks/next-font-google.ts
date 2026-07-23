// Mock for next/font/google — used in vitest (jsdom) environment only.
// next/font functions are build-time only and cannot run in jsdom.
const fontFactory = () => ({
  className: "mock-font",
  variable: "mock-font-variable",
  style: { fontFamily: "mock-font" }
});

export const Inter = fontFactory;
export const Fraunces = fontFactory;
