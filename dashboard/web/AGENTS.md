# AscentIQ frontend

Use Next.js App Router, React, Tailwind v4 and shadcn/ui. No styled-components in any circumstance. No direct CSS-in-JS dependencies or imports. Preserve Next internals. Read version-matched docs from `node_modules/next/dist/docs` before changing Next conventions.

Backend Python is the source of truth. Preserve endpoints, same-origin cookies, X-AscentIQ-Request, revision, save_token, fingerprints and explicit medical consent. Never cache private data in shared server caches, browser storage or the service worker. Query state belongs to a session in memory.

Keep full-width topbar; boxed max1440px content/sidebar; natural-height sidebar; account at top-right. Four main destinations: Dashboard, Workouts, Nutrition, Sleep. Titles inside boxes. Assistant is persistent/nonmodal; check-ins, goals, analyses and meals are modal. Lists10/15; aggregates use the complete period. Missing/zero/pending are distinct.

Commands: npm ci; npm run lint; npm run typecheck; npm run check:styles; npm test; npm run build; npm run test:e2e. Use synthetic data for writing tests. Public repository must never contain personal health records, credentials, private screenshots, databases or exports.

The migrated domain modules preserve working JavaScript business behavior; new infrastructure and shadcn primitives use strict TypeScript. Do not use ts-nocheck, broad any types or ignored build errors to hide problems. Isolate browser globals in effects/handlers; use accessible components and protect dirty/busy forms.
