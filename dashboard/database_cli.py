from __future__ import annotations

import argparse
import json
import os
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from dashboard.repository import (
    CURRENT,
    ROOT,
    PostgresRepository,
    connect,
    contents_digest,
    document_manifest,
    import_operations,
    migrate,
    read_files,
)
from dashboard.snapshot import TZ, build_snapshot


def bootstrap():
    from psycopg import sql

    user = os.environ["PGUSER"]
    database = os.environ["PGDATABASE"]
    with connect(user="ascentiq_admin", password=os.environ["POSTGRES_ADMIN_PASSWORD"], autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,)).fetchone():
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(user), sql.Literal(os.environ["PGPASSWORD"])
                )
            )
        conn.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(database), sql.Identifier(user)))
    migrate()


def initialize_empty():
    """Explicit first-use path; never imports examples or replaces existing data."""
    migrate()
    repo = PostgresRepository()
    revision = repo.active()
    if revision is None:
        revision = repo.publish({}, reason="empty-installation", expected=None)
    return {"initialized": True, "revision": str(revision), "counts": repo.counts()}


def import_data(root):
    migrate()
    repo = PostgresRepository()
    if repo.active() is not None and contents_digest(read_files(root)) != contents_digest(repo.files()[1]):
        raise RuntimeError(
            "Migration import refuses to overwrite newer PostgreSQL data. Export the current revision before any reviewed manual update."
        )
    revision = repo.publish(
        read_files(root),
        reason="json-migration",
        expected=repo.active(),
        snapshot=build_snapshot(root),
        documents=document_manifest(root),
    )
    import_operations(root / "runtime" / "dashboard")
    from psycopg.types.json import Jsonb

    with connect() as conn:
        for path in (root / "runtime" / "dashboard" / "reports").glob("*/meta.json"):
            meta = json.loads(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO athlete.reports(id,metadata) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (meta["id"], Jsonb(meta)),
            )
    return {"revision": str(revision), "counts": repo.counts()}


def validate(root):
    repo = PostgresRepository()
    revision, files = repo.files()
    with tempfile.TemporaryDirectory() as directory:
        local = Path(directory)
        # Build source parity against immutable local originals, not wall-clock reports.
        baseline = build_snapshot(root)
        token = CURRENT.set(files)
        try:
            migrated = build_snapshot(root)
        finally:
            CURRENT.reset(token)
        baseline.pop("generated_at", None)
        migrated.pop("generated_at", None)
        if baseline != migrated:
            raise RuntimeError("Dashboard parity failed")
        if contents_digest(read_files(root)) != contents_digest(files):
            raise RuntimeError("Lossless dataset verification failed")
        repo.export(local)
        if read_files(local) != files:
            raise RuntimeError("Rollback export verification failed")
    return {"equivalent": True, "byte_exact_export": True, "revision": str(revision), "counts": repo.counts()}


def restore_test(archive, output):
    from psycopg import sql

    from dashboard.backup import decrypt, verify

    verification = verify(archive, output / "recovery.key", output)
    database = "ascentiq_restore_" + uuid.uuid4().hex[:12]
    user = os.environ["PGUSER"]
    admin = dict(user="ascentiq_admin", password=os.environ["POSTGRES_ADMIN_PASSWORD"], autocommit=True)
    with connect(**admin) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(user)))
    try:
        with tempfile.TemporaryDirectory(dir=output) as folder:
            temp = Path(folder)
            plain = temp / "restore.tar.gz"
            decrypt(archive, (output / "recovery.key").read_bytes(), plain)
            with tarfile.open(plain, "r:gz") as tar:
                manifest_stream = tar.extractfile("database/manifest.json")
                if manifest_stream is None:
                    raise RuntimeError("Invalid backup format")
                expected = json.load(manifest_stream)
                dump = temp / "postgres.dump"
                dump_stream = tar.extractfile("database/postgres.dump")
                if dump_stream is None:
                    raise RuntimeError("Missing archive entry")
                with dump_stream as source, dump.open("wb") as dest:
                    import shutil

                    shutil.copyfileobj(source, dest)
            env = {**os.environ, "PGDATABASE": database}
            result = subprocess.run(
                ["pg_restore", "--exit-on-error", "--no-owner", "--dbname", database, str(dump)],
                env=env,
                capture_output=True,
            )
            if result.returncode:
                raise RuntimeError("PostgreSQL restore test failed")
            previous = os.environ["PGDATABASE"]
            os.environ["PGDATABASE"] = database
            try:
                restored_revision, actual = PostgresRepository().files()
            finally:
                os.environ["PGDATABASE"] = previous
            if contents_digest(actual) != expected["datasets_digest"] or str(restored_revision) != expected["revision"]:
                raise RuntimeError("Restored datasets differ")
    finally:
        with connect(**admin) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    return {**verification, "postgres_restore": True, "byte_exact": True}


def integration_tests():
    from psycopg import sql

    database = "ascentiq_test_" + uuid.uuid4().hex[:12]
    admin = dict(user="ascentiq_admin", password=os.environ["POSTGRES_ADMIN_PASSWORD"], autocommit=True)
    with connect(**admin) as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(os.environ["PGUSER"])
            )
        )
    try:
        env = {**os.environ, "PGDATABASE": database, "DATABASE_TEST_ENABLED": "1", "DATABASE_BACKEND": "json"}
        first_use = subprocess.run(["python", "-B", "-m", "dashboard.tests.empty_installation_smoke"], env=env)
        if first_use.returncode:
            raise RuntimeError("Empty PostgreSQL installation failed")
        for suite in ("dashboard/tests", "tests"):
            result = subprocess.run(["python", "-B", "-m", "unittest", "discover", "-s", suite], env=env)
            if result.returncode:
                raise RuntimeError("Integration tests failed: " + suite)
    finally:
        with connect(**admin) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    return {"tests_passed": True, "isolated_database": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "bootstrap",
            "init-empty",
            "import",
            "validate",
            "status",
            "export",
            "run",
            "restore-test",
            "test",
            "replace",
        ),
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--mode", choices=("generate", "sync", "sync-garmin", "sync-hevy"), default="generate")
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--dataset",
        choices=(
            "body_metrics",
            "medical_history",
            "physiology_tests",
            "athlete_profile",
            "athlete_preferences",
            "season_goals",
            "mountains_history",
            "nutrition_targets",
            "upcoming_races_2026",
        ),
    )
    args = parser.parse_args()
    result: dict
    if args.command == "bootstrap":
        bootstrap()
        result = {"migrated": True}
    elif args.command == "init-empty":
        result = initialize_empty()
    elif args.command == "test":
        result = integration_tests()
    elif args.command == "import":
        result = import_data(args.root)
    elif args.command == "validate":
        result = validate(args.root)
    elif args.command == "export":
        if args.output is None or args.output.resolve() == args.root.resolve():
            raise RuntimeError("Choose a separate rollback export directory")
        result = {"revision": str(PostgresRepository().export(args.output))}
    elif args.command == "restore-test":
        if args.output is None or args.archive is None:
            raise RuntimeError("Archive and key directory are required")
        result = restore_test(args.archive, args.output)
    elif args.command == "replace":
        from dashboard.database_pipeline import run_database_pipeline
        from dashboard.jobs import JobManager, now

        if not args.dataset or args.input is None:
            raise RuntimeError("A reviewed dataset and input JSON are required")
        raw = args.input.read_bytes()
        json.loads(raw.decode("utf-8-sig"))
        runtime = args.root / "runtime" / "dashboard"
        manager = JobManager(runtime, args.root, recover_interrupted=False)
        key = datetime.now(TZ).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        with manager.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT id FROM jobs WHERE status IN ('queued','running')").fetchone():
                raise RuntimeError("An update is already in progress")
            conn.execute(
                "INSERT INTO jobs VALUES (?, ?, 'running', ?, NULL, 'Atualizacao manual revisada', '[]', NULL)",
                (key, "manual-" + args.dataset, now()),
            )
        try:
            warnings = run_database_pipeline(
                {"id": key, "mode": "generate", "reason": "manual-" + args.dataset},
                args.root,
                runtime,
                replacements={"data/" + args.dataset + ".json": raw},
            )
            manager.update(key, "partial" if warnings else "completed", "Atualizacao manual publicada", warnings)
        except Exception:
            manager.update(key, "failed", "Atualizacao manual nao concluida; consulte a revisao ativa.")
            raise
        result = {"id": key, "dataset": args.dataset, "status": "partial" if warnings else "completed"}
    elif args.command == "run":
        from dashboard.jobs import JobManager

        manager = JobManager(args.root / "runtime" / "dashboard", args.root, recover_interrupted=False)
        key = manager.enqueue(args.mode)
        manager.process(next(job for job in manager.list() if job["id"] == key))
        job = next(job for job in manager.list() if job["id"] == key)
        deadline = time.monotonic() + 7200
        while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(2)
            job = next(job for job in manager.list() if job["id"] == key)
        result = {"id": key, "status": job["status"], "message": job["message"]}
        if job["status"] not in {"completed", "partial"}:
            print(json.dumps(result))
            raise SystemExit(1)
    else:
        repo = PostgresRepository()
        result = {"revision": str(repo.active()), "counts": repo.counts()}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
