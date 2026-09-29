# PostgreSQL storage and recovery

## Architecture

The private application uses PostgreSQL 17 inside Docker. Its database port is
not published. The application role is not a superuser and cannot create roles
or databases. Administrative credentials are passed only to the maintenance
service, not the running API. This is a single-athlete local deployment, not a
multi-tenant hosted service.

Versioned relational projections cover activities, provider IDs, races,
strength sessions, exercises, sets, measurements, medical observations, sleep,
daily performance metrics, and document checksums. Immutable dataset objects
also retain JSONB and original JSON bytes. Large FIT/GPX/PDF files remain in the
private file storage; the database tracks their checksums and relative paths.

The original JSON datasets are migration references, not the current source of
truth. They are mounted read-only in the API. Calculations use an isolated
temporary export of the active PostgreSQL revision. Existing Python formulas
remain unchanged. Calculated data is committed as a new revision in one
transaction. Optimistic revision checks and advisory locks prevent lost writes.
Repeated imports of the same content do not create duplicate records.

Jobs, schedule state, and login sessions also use PostgreSQL. Existing SQLite
records are imported without replacing the local authentication configuration.

## First migration

Configure private `.env` values: `DATABASE_BACKEND=json`, `PGHOST=db`,
`PGPORT=5432`, `PGDATABASE=ascentiq`, `PGUSER=ascentiq_app`, a strong `PGPASSWORD`,
and a different strong `POSTGRES_ADMIN_PASSWORD`. Never commit these values.

1. Pause API writes and create a complete encrypted file backup.
2. Build API and start the database: `docker compose build api` and
   `docker compose up -d db`.
3. Initialize the restricted role and versioned schema:
   `docker compose --profile maintenance run --rm db-tools bootstrap`.
4. Run disposable database tests:
   `docker compose --profile maintenance run --rm db-tools test`.
5. Import the original datasets:
   `docker compose --profile maintenance run --rm db-tools import`.
6. Validate original JSON/dashboard/export parity before rebuilding:
   `docker compose --profile maintenance run --rm db-tools validate`.
7. Create a database backup and test restoration in a separate temporary database.
8. Set `DATABASE_BACKEND=postgres` and run `docker compose up -d`.

Applied migration files are checksum-checked and must never be edited. Add a
new numbered SQL migration for future schema changes. Re-importing stale JSON
over a newer database revision is explicitly refused.

## Regular operation

Use the existing dashboard button or the normal `update_training_data.ps1`
entry point. In PostgreSQL mode this entry point delegates to the transactional
Docker workflow. Custom legacy full-import options fail explicitly rather than
silently writing to obsolete JSON files.

Manual CLI operations:

```powershell
docker compose exec -T api python -m dashboard.database_cli status
docker compose exec -T api python -m dashboard.database_cli run --mode generate
docker compose exec -T api python -m dashboard.database_cli run --mode sync
docker compose exec -T api python -m dashboard.database_cli run --mode sync-garmin
docker compose exec -T api python -m dashboard.database_cli run --mode sync-hevy
```

To update reviewed body/medical/profile records, replace only the explicitly
selected dataset, never the entire old JSON folder:

```powershell
docker compose exec -T api python -m dashboard.database_cli replace --dataset body_metrics --input /app/data/body_metrics.json
```

This reads the supplied JSON as a reviewed input, merges it into an export of
the current database revision, recalculates, validates reports, and atomically
publishes the new revision. Existing activities remain sourced from PostgreSQL.

Provider failures retain the previous canonical records for that provider and
produce a partial status. Successful imports from the other source may still
be committed. Reports are compiled before their database revision is published;
failed/uncommitted reports are not listed by the PostgreSQL API. Historical
reports retain their original snapshots. The live dashboard reads current data,
not the last PDF snapshot. PDF inputs remain training-only.

## Backup and restoration

Backups use AES-256-GCM authenticated encryption and SHA-256 verification of
every archived file. `runtime/backups/recovery.key` is required to decrypt them.
The key is not included in the archives. Local ciphertext and its recovery key
share a disk: this is not protection against compromise of the whole computer.
Keep a separate, secure copy of the key and a verified copy of the encrypted
archives on another device. No external destination is configured automatically.

The workflow verifies a backup once per local day after a successful publication.
It includes a consistent `pg_dump` plus original files and private reports.
A failed backup is reported as a partial job; the committed training data and
previous backup are preserved. Backups are not silently rotated or deleted.

```powershell
docker compose exec -T api python -m dashboard.backup --database
docker compose --profile maintenance run --rm db-tools restore-test --archive /app/runtime/backups/ARCHIVE.tar.gz.enc --output /app/runtime/backups
```

The restore test decrypts into a temporary directory, restores into a newly
created temporary database, compares original dataset bytes, and drops only that
temporary database. It does not restore over the production database.

## Safe rollback

Stop the API before switching storage. Export the latest active PostgreSQL
revision into a separate directory, not over the original migration references:

```powershell
docker compose stop api
docker compose --profile maintenance run --rm db-tools export --output /app/runtime/dashboard/rollback-export
```

Verify the export and copy its datasets to a separate JSON-mode deployment.
Only then switch that deployment to `DATABASE_BACKEND=json`. Also migrate current
operational/session records or use a new login. Do not blindly switch to the old
JSON folder: it does not include changes committed after the migration.

No production volume deletion is part of this procedure. A Docker volume is
persistent storage, not an independent backup. Never use `down -v` for recovery.

## Publication safety

Only source code, SQL migrations, configuration placeholders, and synthetic
tests belong in Git. Never publish `.env`, database dumps, recovery keys, JSON
datasets, actual FIT/GPX/PDF files, provider responses, or private screenshots.
