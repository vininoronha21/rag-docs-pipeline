import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        surface: "#f8fafc",
        line: "#d7dee8",
        accent: "#0f766e"
      }
    }
  },
  plugins: []
};

export default config;
