import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * Flat ESLint config for the website.
 *
 * Note: eslint-config-next was deliberately NOT used:
 * its bundled @rushstack/eslint-patch fails to load
 * under this npm-workspaces install ("calling module
 * was not recognized") for both `next lint` and the
 * ESLint CLI. This standalone config gives the same
 * practical coverage (recommended JS + TypeScript +
 * React Hooks rules) without that broken dependency.
 * Revisit if a future eslint-config-next fixes it.
 */
export default tseslint.config(
  {
    ignores: ["node_modules", ".next", "out", "next-env.d.ts"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    plugins: { "react-hooks": reactHooks },
    rules: reactHooks.configs.recommended.rules,
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
  {
    files: ["**/*.tsx"],
    rules: {
      // React 19 + Next.js: no need to import React.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
