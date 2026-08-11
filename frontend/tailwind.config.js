/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        teal: {
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
        },
        marketing: {
          ink: "#070b14",
          surface: "#0c1220",
          elevated: "#111827",
          border: "#1e293b",
          muted: "#94a3b8",
          dim: "#64748b",
        },
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#bcd3ff",
          300: "#8eb6ff",
          400: "#598dff",
          500: "#3466ff",
          600: "#1d45f5",
          700: "#1633e1",
          800: "#182cb6",
          900: "#1a2c8f",
          950: "#141b57",
        },
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5dae2",
          300: "#b0b9c9",
          400: "#8593aa",
          500: "#66748f",
          600: "#515d76",
          700: "#434c60",
          800: "#3a4152",
          900: "#0e1320",
          950: "#080b14",
        },
      },
      fontFamily: {
        display: [
          "Syne",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        marketing: [
          "DM Sans",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      spacing: {
        18: "4.5rem",
      },
      maxWidth: {
        marketing: "1440px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(16 19 32 / 0.04), 0 1px 3px 0 rgb(16 19 32 / 0.06)",
        elevated:
          "0 4px 6px -1px rgb(16 19 32 / 0.08), 0 2px 4px -2px rgb(16 19 32 / 0.06)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        "float-slow": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" },
        },
        "scan-sweep": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(400%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
        "pulse-dot": "pulse-dot 1.8s ease-in-out infinite",
        "float-slow": "float-slow 6s ease-in-out infinite",
        "pulse-glow": "pulse-glow 3s ease-in-out infinite",
        "scan-sweep": "scan-sweep 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
