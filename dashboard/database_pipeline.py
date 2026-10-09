"""Run unchanged calculators in an isolated workspace, then commit one revision."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from dashboard.pipeline import publish_report, rebuild, sync_sources
from dashboard.repository import PostgresRepository, connect, document_manifest, read_files
from dashboard.settings import default_tz
from dashboard.snapshot import build_snapshot


def backup_if_due(root, runtime, progress):
    from dashboard.backup import create_backup

    output = runtime.parent / "backups"
    latest = output / "latest.json"
    previous = json.loads(latest.read_text()) if latest.exists() else {}
    today = datetime.now(default_tz()).date().isoformat()
    if previous.get("database") and previous.get("local_date") == today:
        return
    progress("Verificando backup criptografado")
    result = create_backup(root, output, database=True)
    result["local_date"] = today
    latest.write_text(json.dumps(result), encoding="utf-8")


def stage_support_files(root: Path, stage: Path) -> None:
    """Copy the code staged calculator subprocesses need to resolve imports."""
    shutil.copytree(root / "scripts", stage / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        root / "dashboard",
        stage / "dashboard",
        ignore=shutil.ignore_patterns("__pycache__", "web", "tests"),
        dirs_exist_ok=True,
    )


def run_database_pipeline(
    job, root, runtime, progress=lambda _: None, *, providers=None, settings=None, replacements=None
):
    from dashboard.provider_settings import ProviderSettings
    from dashboard.repository import LOCK_ID

    providers = providers or ProviderSettings(runtime)

    repo = PostgresRepository()
    # Session lock covers work outside the final SQL transaction, including CLI jobs.
    with connect(autocommit=True) as guard:
        if not guard.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID + 2,)).fetchone()[0]:
            raise RuntimeError("Uma atualizacao ja esta em andamento.")
        try:
            workspaces = runtime / "workspaces"
            workspaces.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=workspaces) as name:
                stage = Path(name)
                revision = repo.export(stage)
                for path, raw in (replacements or {}).items():
                    from dashboard.repository import validate_path

                    validate_path(path)
                    json.loads(raw.decode("utf-8-sig"))
                    target = stage / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                stage_support_files(root, stage)
                sources = (
                    ("garmin",)
                    if job["mode"] == "sync-garmin"
                    else ("hevy",)
                    if job["mode"] == "sync-hevy"
                    else ("garmin", "hevy")
                )
                try:
                    warnings = (
                        sync_sources(
                            stage,
                            progress,
                            sources,
                            credentials={source: providers.credentials(source) for source in sources},
                            enabled={source: providers.enabled(source) for source in sources},
                            settings=settings,
                        )
                        if job["mode"] != "generate"
                        else []
                    )
                finally:
                    # Keep responses even if a later calculation, PDF or transaction fails.
                    for source in ("garmin_mcp_exports", "hevy_api_exports"):
                        for path in (stage / "data" / source).rglob("*"):
                            if path.is_file():
                                target = (
                                    runtime
                                    / "provider_exports"
                                    / source
                                    / job["id"]
                                    / path.relative_to(stage / "data" / source)
                                )
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(path, target)
                    sleep = stage / "data" / "garmin_sleep_reference_2026_04.json"
                    if sleep.exists():
                        target = runtime / "sleep-history" / (job["id"] + ".json")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(sleep, target)
                progress("Recalculando a mesma versao do modelo")
                rebuild(stage, progress)
                snapshot = build_snapshot(stage)
                snapshot["sync_warnings"] = warnings
                files = read_files(stage)
                progress("Gerando relatorios antes da publicacao")
                report = publish_report(snapshot, job["id"], runtime, stage, activate=False, settings=settings)
                progress("Publicando revisao transacional no PostgreSQL")
                # No active data or report pointer changes if SQL validation fails.
                published_revision = repo.publish(
                    files,
                    reason=job.get("reason", job["mode"]),
                    expected=revision,
                    warnings=warnings,
                    report=report,
                    documents=document_manifest(root),
                )
                latest = runtime / "latest.tmp"
                latest.write_text(json.dumps({"id": job["id"]}), encoding="utf-8")
                latest.replace(runtime / "latest.json")
                # Provider responses are archived locally; credentials are never copied.
                try:
                    for source in ("garmin_mcp_exports", "hevy_api_exports"):
                        directory = stage / "data" / source
                        for path in directory.rglob("*"):
                            if path.is_file():
                                target = runtime / "provider_exports" / source / job["id"] / path.relative_to(directory)
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(path, target)
                    for path in (stage / "analysis").rglob("*"):
                        if path.is_file() and path.suffix in {".md", ".svg"}:
                            target = root / path.relative_to(stage)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(path, target)
                except OSError as exc:
                    warnings.append(
                        f"Treinos publicados; copia auxiliar falhou ({Path(exc.filename or 'desconhecido').name}, errno {exc.errno})."
                    )
                try:
                    backup_if_due(root, runtime, progress)
                except Exception:
                    warnings.append(
                        "Treinos publicados; backup automatico nao concluido. Preserve o backup anterior e tente novamente."
                    )
                if warnings:
                    from psycopg.types.json import Jsonb

                    with connect() as conn:
                        conn.execute(
                            "UPDATE athlete.revisions SET warnings=%s WHERE id=%s",
                            (Jsonb(warnings), published_revision),
                        )
                return warnings
        finally:
            guard.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID + 2,))
