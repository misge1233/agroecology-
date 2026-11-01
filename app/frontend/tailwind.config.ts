import type { Config } from "tailwindcss";

/**
 * Design tokens — "Ethiopian highland" palette (U1).
 * Every colour is a CSS variable set in globals.css for light and dark, so
 * components never hard-code a hex. The variables hold RGB channels, consumed
 * as rgb(var(--x) / <alpha-value>) so opacity modifiers (bg-surface/90) work.
 * See docs/design/design_system.md for the measured WCAG contrast of every
 * text/background pair.
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    // 4 px grid is Tailwind's default spacing scale; nothing to override.
    container: { center: true, padding: "1rem" },
    extend: {
      colors: {
        background: "rgb(var(--background) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        foreground: "rgb(var(--text) / <alpha-value>)",
        text: "rgb(var(--text) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          hover: "rgb(var(--primary-hover) / <alpha-value>)",
          fg: "rgb(var(--primary-fg) / <alpha-value>)",
          soft: "rgb(var(--primary-soft) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--secondary) / <alpha-value>)",
          fg: "rgb(var(--secondary-fg) / <alpha-value>)",
          text: "rgb(var(--secondary-text) / <alpha-value>)",
          soft: "rgb(var(--secondary-soft) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          fg: "rgb(var(--accent-fg) / <alpha-value>)",
          text: "rgb(var(--accent-text) / <alpha-value>)",
          soft: "rgb(var(--accent-soft) / <alpha-value>)",
        },
        success: {
          DEFAULT: "rgb(var(--success) / <alpha-value>)",
          text: "rgb(var(--success-text) / <alpha-value>)",
          soft: "rgb(var(--success-soft) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "rgb(var(--warning) / <alpha-value>)",
          text: "rgb(var(--warning-text) / <alpha-value>)",
          soft: "rgb(var(--warning-soft) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "rgb(var(--danger) / <alpha-value>)",
          text: "rgb(var(--danger-text) / <alpha-value>)",
          soft: "rgb(var(--danger-soft) / <alpha-value>)",
        },
        // Footer / CTA band: theme-aware deep green.
        band: {
          DEFAULT: "rgb(var(--brand-band) / <alpha-value>)",
          fg: "rgb(var(--brand-band-fg) / <alpha-value>)",
          muted: "rgb(var(--brand-band-muted) / <alpha-value>)",
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
          1: "rgb(var(--chart-1) / <alpha-value>)",
          2: "rgb(var(--chart-2) / <alpha-value>)",
          3: "rgb(var(--chart-3) / <alpha-value>)",
          4: "rgb(var(--chart-4) / <alpha-value>)",
          5: "rgb(var(--chart-5) / <alpha-value>)",
          6: "rgb(var(--chart-6) / <alpha-value>)",
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
