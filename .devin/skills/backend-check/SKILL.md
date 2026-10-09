---
name: backend-check
description: Run the Python backend verification suite (tests, lint, types) exactly as CI does
allowed-tools:
  - read
  - grep
  - glob
  - exec
permissions:
  allow:
    - Exec(.venv/Scripts/python.exe)
    - Exec(git status)
    - Exec(git diff)
---

Verify the Python backend in `dashboard/` the same way `.github/workflows/platform.yml` does.

Environment: use the project venv at `.venv/Scripts/python.exe` (create with
`py -3.14 -m venv .venv` and `pip install -r dashboard/requirements-dev.txt` if missing).
Always set `PYTHONUTF8=1`. Run from the repository root.
Tests require a disposable PostgreSQL with `CREATEDB` (tests create one database per
class from a migrated template): `PGHOST=localhost PGPORT=5433 PGUSER=postgres
PGPASSWORD=synthetic-local-password PGDATABASE=ascentiq_test_local` against a
throwaway `postgres:17` container (`ascentiq-test-db`).

Run, in order, and stop at the first failure:

1. `python -m ruff check .` and `python -m ruff format --check .`
2. `python -m mypy`
3. `python -B -m dashboard.tests.empty_installation_smoke`
4. `python -B -m pytest` (the pyproject testpaths cover `dashboard/tests` and `tests`)
5. `python -m dashboard.openapi_export --check`

Rules that apply to every backend change:

- Backend Python is the source of truth for the API. Preserve endpoints, same-origin cookie auth,
  the `X-AscentIQ-Request` CSRF header, `revision` / `expected_revision` optimistic concurrency,
  `save_token`, data fingerprints and explicit medical consent flags.
- Error messages shown to the user are in Brazilian Portuguese; keep existing wording when refactoring.
- Private data never goes to disk caches, shared caches or logs. In-memory only, keyed by revision.
- Missing, zero and pending are distinct states; never collapse `None` into `0`.
- Application code never writes to `os.environ`; tests use `settings.override(...)` instead of `patch.dict(os.environ, ...)`.
- Tests use synthetic data only. Never read `data/*.json` (except `sample_*.json`), `runtime/` or `.env` in tests.
- Do not touch the running Docker stack (`ascentiq-*` containers) or `compose.override.yaml`.

Report the result of each step verbatim (pass/fail counts, first failing test with traceback).
