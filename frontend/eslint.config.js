import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const nodeGlobals = {
  console: "readonly",
  process: "readonly",
  URL: "readonly",
  fetch: "readonly",
  setTimeout: "readonly",
};

export default defineConfig(
  globalIgnores([
    "dist",
    "coverage",
    "playwright-report",
    "test-results",
    "src/api/schema.d.ts",
  ]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Plan §2.2: the prototype rendered HTML strings; the rebuild never does.
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[property.name=/^(innerHTML|outerHTML)$/]",
          message: "Render with React instead of writing HTML strings.",
        },
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Render with React instead of injecting HTML.",
        },
      ],
      // Plan §2.2: blocking native dialogs are replaced by in-page components.
      "no-restricted-globals": [
        "error",
        { name: "prompt", message: "Use the Dialog component." },
        { name: "alert", message: "Use the toast or an inline message." },
        { name: "confirm", message: "Use the Dialog component." },
      ],
      "no-restricted-properties": [
        "error",
        {
          object: "window",
          property: "prompt",
          message: "Use the Dialog component.",
        },
        { object: "window", property: "alert", message: "Use the toast." },
        {
          object: "window",
          property: "confirm",
          message: "Use the Dialog component.",
        },
      ],
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        { allowNumber: true },
      ],
    },
  },
  {
    files: ["**/*.{js,mjs}"],
    extends: [js.configs.recommended],
    languageOptions: { globals: nodeGlobals },
  },
);
