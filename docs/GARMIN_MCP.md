# Garmin MCP Integration

AscentIQ treats Garmin MCP as an import layer, not as the analytical source of truth.

The recommended flow is:

1. Garmin MCP reads Garmin Connect.
2. AscentIQ stores a local JSON snapshot under `data/garmin_mcp_exports/`.
3. AscentIQ normalizes that snapshot into `data/training_history.json` and the sleep reference JSON.
4. The performance model reads the local AscentIQ database.

This keeps the analytics reproducible, versionable, and private.

## Install Optional Dependencies

```bash
python -m pip install -r requirements-mcp.txt
```

The default bridge is configured for the community `mcp-garmin` server. It is not an official Garmin product.

## Authentication

Do not commit credentials or Garmin tokens.

For `mcp-garmin`, set credentials in your shell environment:

```powershell
$env:GARMIN_EMAIL = "you@example.com"
$env:GARMIN_PASSWORD = "your-password"
```

Then run the first-time login if your server requires it:

```powershell
uvx mcp-garmin-login
```

If Garmin asks for MFA, complete it interactively. Tokens are managed by the MCP server outside this repository.

## Capture A Snapshot

For day-to-day use on Windows, the easiest path is the interactive full import runner:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_garmin_mcp_full_import.ps1 `
  -StartDate 2024-01-01 `
  -EndDate 2026-06-08
```

If `GARMIN_EMAIL` and `GARMIN_PASSWORD` are not already set in that PowerShell process, the runner prompts for them without storing credentials in the repository. It then captures the Garmin MCP snapshot, imports it into the local AscentIQ database, deduplicates existing Garmin CSV rows, and rebuilds the performance models/charts.

The runner also supports a lighter detail pass:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_garmin_mcp_full_import.ps1 `
  -StartDate 2026-01-01 `
  -EndDate 2026-06-08 `
  -MaxDetailActivities 100
```

For a smaller manual snapshot:

```powershell
python scripts\fetch_garmin_mcp_snapshot.py --start-date 2026-06-01 --end-date 2026-06-08
```

By default this launches:

```text
uvx mcp-garmin
```

You can override the server command:

```powershell
python scripts\fetch_garmin_mcp_snapshot.py `
  --server-command uvx `
  --server-arg mcp-garmin `
  --start-date 2026-06-01 `
  --end-date 2026-06-08
```

The snapshot is written to `data/garmin_mcp_exports/`.

## Import A Snapshot

```powershell
python scripts\import_garmin_mcp_snapshot.py --input data\garmin_mcp_exports
python scripts\build_performance_management_model.py
python scripts\build_last_3_weeks_pmc_chart.py
```

The import is deduplicated. If an activity already exists from Garmin CSV export, the MCP copy is merged into the existing row and can enrich it with Garmin activity IDs, moving time, HR, and elevation instead of creating a duplicate. Garmin aliases such as `mountaineering` and `stair_climbing` are normalized to the local activity schema.

## Why Two Scripts?

- `fetch_garmin_mcp_snapshot.py` deals with Garmin/MCP authentication and live APIs.
- `import_garmin_mcp_snapshot.py` deals with AscentIQ's stable local schema.

This separation protects the project if Garmin changes private endpoints or a community MCP server changes tool names.

## Security Notes

- Prefer read-only Garmin MCP servers.
- Do not expose write tools to the coaching agent.
- Do not commit raw snapshots unless they are sanitized.
- Keep `data/garmin_mcp_exports/` private.
