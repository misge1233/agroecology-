import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Native ESLint flat config (eslint-config-next >= 16 ships flat configs
// directly; the former FlatCompat/@eslint/eslintrc shim no longer loads it).
// `next lint` was removed in Next 16, so `npm run lint` now calls eslint directly.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // eslint-plugin-react-hooks >= 6 (pulled in by eslint-config-next 16)
    // adds React-Compiler-era rules that flag long-standing, working patterns
    // in this codebase (SSR-safe reads of localStorage/sessionStorage on
    // mount, prop -> input-field sync effects, the "latest callback" ref).
    // Keep them visible as warnings; refactoring those components is tracked
    // as a separate follow-up, not part of the Next 16 dependency fix.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules/**",
  ]),
]);

export default eslintConfig;
