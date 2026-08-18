import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        canvas: "var(--canvas)",
        panel: "var(--panel)",
        elevated: "var(--elevated)",
        ink: "var(--ink)",
        body: "var(--body)",
        mute: "var(--mute)",
        edge: "var(--edge)",
        leaf: {
          DEFAULT: "var(--leaf)",
          deep: "var(--leaf-deep)",
          bright: "var(--leaf-bright)",
        },
        soil: "var(--soil)",
        accent: "var(--accent)",
        success: "var(--success)",
        warning: "var(--warning)",
        error: "var(--error)",
        brand: {
          blue: "var(--brand-blue)",
          violet: "var(--brand-violet)",
          pink: "var(--brand-pink)",
          teal: "var(--brand-teal)",
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
        display: ["var(--font-display)", "Georgia", "serif"],
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      letterSpacing: {
        tighter: "-0.04em",
        widest: "0.18em",
      },
      maxWidth: {
        "8xl": "88rem",
      },
      keyframes: {
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "marquee-reverse": {
          "0%": { transform: "translateX(-50%)" },
          "100%": { transform: "translateX(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "0.95" },
        },
      },
      animation: {
        marquee: "marquee 32s linear infinite",
        "marquee-reverse": "marquee-reverse 36s linear infinite",
        float: "float 6s ease-in-out infinite",
        "pulse-glow": "pulseGlow 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
