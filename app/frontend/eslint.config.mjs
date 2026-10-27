import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Native ESLint flat config (eslint-config-next >= 16 ships flat configs
// directly). `next lint` was removed in Next 16, so `npm run lint` calls
// eslint directly.
//
// U1 quality bar: 0 errors, 0 warnings. The two React-Compiler-era hook rules
// that were downgraded to `warn` on 15 Oct (follow-up F-1) are back at `error`;
// the components they flagged were refactored (useSyncExternalStore for
// storage/media-query reads, derived state instead of prop→state effects).
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/refs": "error",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules/**",
    "vitest.setup.ts",
  ]),
]);

export default eslintConfig;
