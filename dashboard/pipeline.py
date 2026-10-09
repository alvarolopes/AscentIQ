from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from dashboard.settings import default_tz
from dashboard.snapshot import ROOT


def run_script(
    name: str, *arguments: str, root: Path = ROOT, progress=lambda _: None, environment: dict | None = None
) -> None:
    progress(name.removesuffix(".py").replace("_", " "))
    child = dict(os.environ) if environment is None else environment
    child["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / name), *map(str, arguments)],
        cwd=root,
        env=child,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
    )
    if result.returncode:
        # Connector output can contain identifiers/secrets. Never publish it through the dashboard.
        raise RuntimeError(
            f"Falha na etapa {name}; código {result.returncode}. Verifique a conexão e as credenciais locais."
        )


def sync_sources(
    root: Path = ROOT,
    progress=lambda _: None,
    sources=("garmin", "hevy"),
    *,
    credentials: dict | None = None,
    enabled: dict | None = None,
    settings=None,
) -> list[str]:
    from dashboard.settings import current
    from scripts.compute_garmin_sync_window import sync_start

    settings = settings or current()
    credentials = credentials or {}
    enabled = enabled or {}
    keys = {"garmin": ("email", "password"), "hevy": ("api_key",)}
    child_secrets = {
        "garmin": lambda c: {"GARMIN_EMAIL": c.get("email", ""), "GARMIN_PASSWORD": c.get("password", "")},
        "hevy": lambda c: {"HEVY_API_KEY": c.get("api_key", "")},
    }
    warnings = []
    available = []
    for source in sources:
        if not enabled.get(source, True):
            warnings.append(f"Integração {source} desconectada; histórico preservado.")
        elif any(not credentials.get(source, {}).get(key) for key in keys[source]):
            warnings.append(f"Integração {source} sem credenciais; configure em Dados / Integrações.")
        else:
            available.append(source)
    if not available:
        raise RuntimeError("Nenhuma fonte disponível. Configure as integrações antes de sincronizar.")
    sources = tuple(available)
    today = datetime.now(default_tz()).date()
    history_path = root / 'data' / 'training_history.json'
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if not history_path.exists():
        history_path.write_text('[]', encoding='utf-8')
    history = json.loads(history_path.read_text(encoding="utf-8-sig"))
    start = sync_start(history, today, settings.sync_start_date, 7)
    # Catch up sleep independently of activity dates after a missed collection.
    from scripts.sleep_data import sleep_rows

    sleep_path = root / "data" / "garmin_sleep_reference_2026_04.json"
    if sleep_path.exists():
        rows = sleep_rows(json.loads(sleep_path.read_text(encoding="utf-8-sig")), today.isoformat())
        if rows:
            start = min(start, date.fromisoformat(rows[-1]['date']) - timedelta(days=7))
    stamp = datetime.now(default_tz()).strftime("%Y%m%d_%H%M%S")
    output = root / "data" / "garmin_mcp_exports" / f"garmin_mcp_incremental_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "--server-command",
        settings.garmin_mcp_command,
        "--all-activities",
        "--max-activities",
        str(settings.sync_max_activities),
        "--start-date",
        str(start),
        "--end-date",
        today.isoformat(),
        "--output",
        str(output),
        "--known-activity-history",
        str(root / "data" / "training_history.json"),
        "--skip-profile",
        "--daily-tool",
        "get_daily_summary",
        "--max-detail-activities",
        str(settings.sync_max_detail_activities),
    ]
    for tool in (
        "get_activity",
        "get_activity_details",
        "get_activity_splits",
        "get_activity_hr_zones",
        "get_activity_exercise_sets",
    ):
        args += ["--activity-detail-tool", tool]
    for source in sources:
        original_datasets = {p: p.read_bytes() for p in (root / "data").glob("*.json")}
        original_history = (root / "data" / "training_history.json").read_bytes()
        original_hevy = {p: p.read_bytes() for p in (root / "data").glob("*hevy*.json")}
        consolidated = root / "data" / "strength_training_consolidated.json"
        original_consolidated = consolidated.read_bytes() if consolidated.exists() else None
        try:
            if source == "garmin":
                run_script(
                    "fetch_garmin_mcp_snapshot.py",
                    *args,
                    root=root,
                    progress=progress,
                    environment={**os.environ, **child_secrets["garmin"](credentials.get("garmin", {}))},
                )
                run_script(
                    "import_garmin_mcp_snapshot.py",
                    "--input",
                    str(output),
                    "--since",
                    str(start),
                    root=root,
                    progress=progress,
                )
                payload = json.loads(output.read_text(encoding="utf-8-sig"))
                if '"error"' in json.dumps(
                    {key: payload.get(key) for key in ("sleep", "daily_metrics", "activity_details")}
                ):
                    warnings.append(
                        "Garmin retornou dados complementares parciais; confira a atualidade de cada fonte."
                    )
                stored_sleep = json.loads(sleep_path.read_text(encoding="utf-8-sig")) if sleep_path.exists() else {}
                if not any(
                    row.get('date') == today.isoformat() and row.get('duration_minutes') is not None
                    for row in stored_sleep.get('daily', [])
                ):
                    warnings.append(
                        "Sono de hoje ainda sem duração disponível no Garmin. O histórico anterior foi preservado; sincronize o relógio."
                    )
            else:
                output_hevy = root / "data" / "hevy_api_exports" / "hevy_workouts_latest.json"
                run_script(
                    "fetch_hevy_workouts.py",
                    "--output",
                    str(output_hevy),
                    "--incremental",
                    "--no-archive",
                    root=root,
                    progress=progress,
                    environment={**os.environ, **child_secrets["hevy"](credentials.get("hevy", {}))},
                )
                run_script(
                    "import_hevy_workouts.py",
                    "--input",
                    str(output_hevy),
                    "--format",
                    "api",
                    root=root,
                    progress=progress,
                )
        except RuntimeError, subprocess.TimeoutExpired:
            for p, raw in original_datasets.items():
                p.write_bytes(raw)
            (root / "data" / "training_history.json").write_bytes(original_history)
            for p, raw in original_hevy.items():
                p.write_bytes(raw)
            if original_consolidated is not None:
                consolidated.write_bytes(original_consolidated)
            warnings.append(f"Importação {source} não concluída. Os dados anteriores dessa fonte foram preservados.")
    return warnings


def rebuild(root: Path = ROOT, progress=lambda _: None) -> None:
    # First use has no observation from which to derive training load. The
    # legacy scripts intentionally reject empty input; publish missing metrics
    # rather than failing the entire report or using portfolio examples.
    data = root / 'data'
    activities = []
    for name in ('training_history', 'race_history'):
        path = data / (name + '.json')
        if path.exists():
            activities.extend(json.loads(path.read_text(encoding='utf-8-sig')))
    if not any(isinstance(row, dict) and row.get('date') for row in activities):
        data.mkdir(parents=True, exist_ok=True)
        (data / 'performance_management_model.json').write_text(
            json.dumps(
                {
                    'summary': {},
                    'daily_series': [],
                    'model_notes': ['Sem atividades datadas para estimar a carga. Ausência não significa descanso.'],
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        progress('Sem atividades datadas; métricas de carga permanecem desconhecidas')
        return
    for name in (
        "build_performance_management_model.py",
        "build_last_3_weeks_pmc_chart.py",
        "build_training_execution_indexes.py",
        "build_current_performance_dashboard.py",
        "build_training_sync_summary.py",
    ):
        run_script(name, root=root, progress=progress)


def chart_svg(rows: list[dict], dark: bool = False) -> str:
    width, height, margin = 1080, 340, 52
    keys = [("fitness", "#126a61", "Fitness"), ("fatigue", "#c46540", "Fadiga"), ("form", "#b28b22", "Forma")]
    if dark:
        keys = [("fitness", "#3fb950", "Fitness"), ("fatigue", "#f78166", "Fadiga"), ("form", "#d29922", "Forma")]
    background, grid, label = ("#0d1117", "#30363d", "#8b949e") if dark else ("#fcfaf5", "#dedbd2", "#62675f")
    values = [float(row[key]) for row in rows for key, _, _ in keys if row.get(key) is not None]
    lo, hi = min(values + [0]), max(values + [1])
    span = hi - lo or 1
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{background}"/>',
    ]
    for index in range(5):
        value = lo + span * index / 4
        y = height - margin - (height - margin * 2) * index / 4
        svg.append(f'<line x1="{margin}" y1="{y}" x2="{width - margin}" y2="{y}" stroke="{grid}"/>')
        svg.append(f'<text x="8" y="{y + 4}" fill="{label}" font-size="12">{value:.0f}</text>')
    for key, color, title in keys:
        points = []
        for i, row in enumerate(rows):
            if row.get(key) is not None:
                x = margin + (width - margin * 2) * i / max(1, len(rows) - 1)
                y = height - margin - (float(row[key]) - lo) / span * (height - margin * 2)
                points.append(f"{x:.1f},{y:.1f}")
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        svg.append(
            f'<text x="{650 + keys.index((key, color, title)) * 130}" y="22" fill="{color}" font-size="14">{title}</text>'
        )
    if rows:
        for x, row in ((margin, rows[0]), (width - margin - 75, rows[-1])):
            svg.append(f'<text x="{x}" y="{height - 15}" fill="{label}" font-size="12">{escape(row["date"])}</text>')
    return "\n".join(svg + ["</svg>"])


def training_snapshot(snapshot: dict) -> dict:
    # PDF input is an allowlist: medical/body/nutrition fields cannot reach the template.
    result = {
        key: snapshot[key]
        for key in (
            "report_id",
            "generated_at",
            "as_of",
            "model_version",
            "source_digest",
            "week",
            "activities",
            "strength",
        )
        if key in snapshot
    }
    result["freshness"] = {"activities": snapshot["freshness"].get("activities")}
    result["athlete"] = {
        "name": snapshot["athlete"].get("name"),
        "current_goal": snapshot["athlete"].get("endurance_goal"),
    }
    result["performance"] = {
        "summary": {key: snapshot["performance"]["summary"].get(key) for key in ("fitness", "fatigue", "form")},
        "series": [
            {key: row.get(key) for key in ("date", "fitness", "fatigue", "form", "daily_load")}
            for row in snapshot["performance"]["series"]
        ],
    }
    result["insights"] = [
        "Fitness, Fadiga e Forma sao indices do modelo local de carga, nao TSS oficial nem percentuais de condicionamento.",
        "A carga usa Garmin/Strava com detalhes Hevy vinculados; sessoes somente do Hevy aparecem no diario de forca, sem adicao automatica a curva.",
        "Sessoes vinculadas ao Garmin e ao Hevy nao sao contadas duas vezes no diario de forca.",
    ]
    result["sync_warnings"] = snapshot.get("sync_warnings", [])
    return result


def publish_report(
    snapshot: dict, job_id: str, runtime: Path, root: Path = ROOT, activate: bool = True, *, settings=None
) -> dict:
    staging = runtime / "staging" / job_id
    staging.mkdir(parents=True, exist_ok=False)
    try:
        snapshot["report_id"] = job_id
        (staging / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "training-report.json").write_text(
            json.dumps(training_snapshot(snapshot), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (staging / "performance.svg").write_text(chart_svg(snapshot["performance"]["series"][-90:]), encoding="utf-8")
        (staging / "performance-dark.svg").write_text(
            chart_svg(snapshot["performance"]["series"][-90:], dark=True), encoding="utf-8"
        )
        shutil.copy2(root / "dashboard" / "templates" / "weekly.typ", staging / "weekly.typ")
        for name in ("dashboard-html.typ", "report.css"):
            shutil.copy2(root / "dashboard" / "templates" / name, staging / name)
        if settings is None:
            from dashboard.settings import current

            settings = current()
        typst = settings.typst_bin
        subprocess.run(
            [typst, "compile", "--root", str(staging), str(staging / "weekly.typ"), str(staging / "report.pdf")],
            check=True,
            capture_output=True,
            timeout=120,
        )
        subprocess.run(
            [
                typst,
                "compile",
                "--features",
                "html",
                "--root",
                str(staging),
                str(staging / "dashboard-html.typ"),
                str(staging / "dashboard.html"),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if (staging / "report.pdf").stat().st_size < 1000:
            raise RuntimeError("Relatório PDF vazio.")
        if "Baixar PDF" not in (staging / "dashboard.html").read_text(encoding="utf-8"):
            raise RuntimeError("Dashboard HTML incompleto.")
        metadata = {
            "id": job_id,
            "generated_at": snapshot["generated_at"],
            "as_of": snapshot["as_of"],
            "source_digest": snapshot["source_digest"],
            "model_version": snapshot["model_version"],
            "period": snapshot["week"],
            "warnings": snapshot.get("sync_warnings", []),
            "pdf_scope": "training",
        }
        (staging / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        archive = runtime / "reports" / job_id
        archive.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(archive)
        if activate:
            latest = runtime / "latest.tmp"
            latest.write_text(json.dumps({"id": job_id}), encoding="utf-8")
            latest.replace(runtime / "latest.json")
        return metadata
    except Exception:
        # A failed compile never changes the published report; staging remains for local diagnosis.
        raise
