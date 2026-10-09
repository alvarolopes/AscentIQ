import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,
  {
    // Preserved domain modules hydrate browser-only state and synchronize remote
    // forms without overwriting unsaved drafts. React Compiler is not enabled.
    // Keep every other hooks rule active, including refs and exhaustive-deps.
    files: ['src/features/{settings,documents,assistant,profile,pwa}/**/*.jsx'],
    rules: {'react-hooks/set-state-in-effect': 'off'},
  },
  {
    rules: {
      'no-restricted-imports': ['error', { patterns: ['styled-components', '@emotion/*', 'styled-jsx', 'styled-jsx/*'] }],
    },
  },
  globalIgnores(['.next/**', 'next-env.d.ts']),
]);
