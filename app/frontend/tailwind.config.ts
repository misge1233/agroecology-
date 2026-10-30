import type { Config } from "tailwindcss";

/**
 * Design tokens — "Ethiopian highland" palette (U1).
 * Every colour is a CSS variable set in globals.css for light and dark, so
 * components never hard-code a hex. See docs/design/design_system.md for the
 * measured WCAG contrast of every text/background pair.
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    // 4 px grid is Tailwind's default spacing scale; nothing to override.
    container: { center: true, padding: "1rem" },
    extend: {
      colors: {
        background: "var(--background)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        foreground: "var(--text)",
        text: "var(--text)",
        muted: "var(--muted)",
        border: "var(--border)",
        ring: "var(--ring)",
        primary: {
          DEFAULT: "var(--primary)",
          hover: "var(--primary-hover)",
          fg: "var(--primary-fg)",
          soft: "var(--primary-soft)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          fg: "var(--secondary-fg)",
          text: "var(--secondary-text)",
          soft: "var(--secondary-soft)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          fg: "var(--accent-fg)",
          text: "var(--accent-text)",
          soft: "var(--accent-soft)",
        },
        success: {
          DEFAULT: "var(--success)",
          text: "var(--success-text)",
          soft: "var(--success-soft)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          text: "var(--warning-text)",
          soft: "var(--warning-soft)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          text: "var(--danger-text)",
          soft: "var(--danger-soft)",
        },
        // Footer / CTA band: theme-aware deep green.
        band: {
          DEFAULT: "var(--brand-band)",
          fg: "var(--brand-band-fg)",
          muted: "var(--brand-band-muted)",
        },
        // Fixed (theme-independent) forest scale for text and scrims laid over
        // photography, where the page theme does not apply (U3 hero).
        forest: {
          50: "#eef6f1",
          200: "#bfe3cd",
          800: "#124a31",
          900: "#0d3b27",
          950: "#082518",
        },
        chart: {
          1: "var(--chart-1)",
          2: "var(--chart-2)",
          3: "var(--chart-3)",
          4: "var(--chart-4)",
          5: "var(--chart-5)",
          6: "var(--chart-6)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        ethiopic: ["var(--font-ethiopic)", "var(--font-sans)", "sans-serif"],
      },
      // Type scale 12 / 14 / 16 / 18 / 22 / 28 / 36 / 44 / 56 px; body 1.5,
      // headings 1.2, display sizes (4xl/5xl, hero and page titles) tighter.
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.5" }],
        sm: ["0.875rem", { lineHeight: "1.5" }],
        base: ["1rem", { lineHeight: "1.5" }],
        lg: ["1.125rem", { lineHeight: "1.55" }],
        xl: ["1.375rem", { lineHeight: "1.3" }],
        "2xl": ["1.75rem", { lineHeight: "1.2" }],
        "3xl": ["2.25rem", { lineHeight: "1.15" }],
        "4xl": ["2.75rem", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
        "5xl": ["3.5rem", { lineHeight: "1.05", letterSpacing: "-0.025em" }],
      },
      borderRadius: {
        control: "0.5rem", // 8 px controls
        card: "0.75rem", // 12 px cards
        panel: "1rem", // 16 px feature panels (stats, CTA band)
      },
      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
      },
      transitionDuration: {
        fast: "120ms",
        base: "200ms",
      },
      maxWidth: {
        content: "80rem",
      },
    },
  },
  plugins: [],
};

export default config;
