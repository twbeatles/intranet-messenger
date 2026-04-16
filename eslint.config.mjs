import js from "@eslint/js";
import globals from "globals";

const browserGlobals = {
  ...globals.browser,
  ...globals.es2021,
  CryptoJS: "readonly",
  E2E: "readonly",
  io: "readonly",
  MessengerApp: "readonly",
  MessengerNotification: "readonly",
  MessengerStorage: "readonly",
  MessengerUpload: "readonly",
};

const sharedRules = {
  ...js.configs.recommended.rules,
  "no-empty": "off",
  "no-redeclare": "off",
  "no-undef": "off",
  "no-unused-vars": "off",
};

export default [
  {
    ignores: [
      "node_modules/**",
      "static/js/**/*.min.js",
    ],
  },
  {
    files: ["static/js/experimental/modules/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: browserGlobals,
    },
    rules: sharedRules,
  },
  {
    files: ["static/js/**/*.js"],
    ignores: ["static/js/experimental/modules/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: browserGlobals,
    },
    rules: sharedRules,
  },
];
