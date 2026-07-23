import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0F172A",
        surface: "#111827",
        sidebar: "#0B1220",
        card: "#1E293B",
        border: "#334155",
        primary: "#2563EB",
        "primary-hover": "#1D4ED8",
        success: "#22C55E",
        warning: "#F59E0B",
        critical: "#DC2626",
      },
      borderRadius: { card: "16px", button: "12px" },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
