import js from "@eslint/js";
import tseslint from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
import globals from "globals";

// Correctness only; generated contracts and imported registry source have separate owners.
export default [
  { ignores: ["dist/**", "node_modules/**", "src/api/types.ts", "src/registry/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser, globals: { ...globals.browser, ...globals.node } },
    plugins: { "@typescript-eslint": tseslint.plugin, "react-hooks": hooks },
    rules: {
      ...js.configs.recommended.rules,
      ...tseslint.configs.recommended[2].rules,
      "no-undef": "off", // TypeScript checks browser, type and import names.
      "@typescript-eslint/no-explicit-any": "off", // Existing chart/serialization adapters use dynamic shapes.
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "react-hooks/rules-of-hooks": "error",
    },
  },
];
