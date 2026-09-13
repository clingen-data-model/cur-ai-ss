/* ESLint flat config.
 *
 * `pnpm lint` was in package.json and every plugin was installed, but this file
 * never was -- so ESLint exited 2 with "couldn't find an eslint.config.*" and
 * linted nothing. It looked like a lint step for as long as nobody read the
 * output.
 */
import js from '@eslint/js'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import tsParser from '@typescript-eslint/parser'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'

export default [
  {
    // Generated or built, and none of it is ours to fix. src/api/generated is
    // rewritten by `pnpm build`; vite.config.js/.d.ts are tsc output sitting
    // next to their source (see .gitignore).
    ignores: [
      'dist/**',
      'src/api/generated/**',
      'vite.config.js',
      'vite.config.d.ts',
      'eslint.config.js',
    ],
  },
  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser, ...globals.es2021 },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'error',
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // TypeScript already reports unused locals and undefined names, and does
      // it with type information -- base ESLint's versions only duplicate the
      // first and get the second wrong on type-only identifiers.
      'no-unused-vars': 'off',
      'no-undef': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
]
