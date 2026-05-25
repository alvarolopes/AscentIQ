from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import fitdecode


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_duration_to_seconds(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(round(float(parts[2])))
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(round(float(parts[1])))
    return None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("km", "").replace("m", "").replace("bpm", "").replace("%", "").strip()
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    elif text.count(",") >= 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def fmt_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    total_seconds = int(round(seconds_per_km))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}/km"


def round_or_none(value: float | None, decimals: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, decimals)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def segment_summary_from_laps(laps: list[dict[str, Any]], section: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not section:
        return None
    distance = sum(item["distance_km"] for item in section)
    timer_s = sum(item["timer_s"] for item in section)
    hr_values = [item["avg_hr"] for item in section if item.get("avg_hr") is not None]
    pace = (timer_s / distance) if distance else None
    return {
        "distance_km": round(distance, 3),
        "pace_s_per_km": round(pace, 1) if pace is not None else None,
        "pace_avg": fmt_pace(pace),
        "ascent_m": sum(item["ascent_m"] for item in section),
        "descent_m": sum(item["descent_m"] for item in section),
        "avg_hr": round(mean(hr_values), 1) if hr_values else None,
    }


def parse_fit_file(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    session: dict[str, Any] | None = None
    laps: list[dict[str, Any]] = []
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as handle:
        with fitdecode.FitReader(handle) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name not in {"session", "lap"}:
                    continue
                fields = {field.name: field.value for field in frame.fields}
                if frame.name == "session":
                    session = fields
                elif frame.name == "lap":
                    laps.append(fields)
    return session, laps


def summarize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cumulative_km = 0.0
    for index, lap in enumerate(laps, start=1):
        distance_km = (lap.get("total_distance") or 0.0) / 1000.0
        timer_s = float(lap.get("total_timer_time") or 0.0)
        elapsed_s = float(lap.get("total_elapsed_time") or 0.0)
        pace_s_per_km = (timer_s / distance_km) if distance_km else None
        cumulative_km += distance_km
        items.append(
            {
                "lap_index": index,
                "distance_km": round(distance_km, 3),
                "cumulative_km": round(cumulative_km, 3),
                "timer_s": round(timer_s, 3),
                "elapsed_s": round(elapsed_s, 3),
                "pace_s_per_km": round(pace_s_per_km, 1) if pace_s_per_km is not None else None,
                "pace_avg": fmt_pace(pace_s_per_km),
                "ascent_m": int(lap.get("total_ascent") or 0),
                "descent_m": int(lap.get("total_descent") or 0),
                "avg_hr": lap.get("avg_heart_rate"),
                "max_hr": lap.get("max_heart_rate"),
                "avg_power": lap.get("avg_power"),
                "avg_running_cadence": lap.get("avg_running_cadence"),
                "altitude_min_m": round(float(lap.get("enhanced_min_altitude") or 0.0), 1),
                "altitude_max_m": round(float(lap.get("enhanced_max_altitude") or 0.0), 1),
            }
        )
    return items


def build_finish_analysis(lap_items: list[dict[str, Any]], activity_type: str) -> dict[str, Any] | None:
    if activity_type not in {"Run", "Hike", "Walk"}:
        return None
    full_km_laps = [item for item in lap_items if item["distance_km"] > 0.95]
    if len(full_km_laps) < 6:
        return None

    last_five = segment_summary_from_laps(lap_items, full_km_laps[-5:])
    previous_five = segment_summary_from_laps(lap_items, full_km_laps[-10:-5]) if len(full_km_laps) >= 10 else None
    last_two = segment_summary_from_laps(lap_items, full_km_laps[-2:])
    previous_two = segment_summary_from_laps(lap_items, full_km_laps[-4:-2]) if len(full_km_laps) >= 4 else None

    last_five_gain = None
    if last_five and previous_five and last_five.get("pace_s_per_km") is not None and previous_five.get("pace_s_per_km") is not None:
        last_five_gain = round(previous_five["pace_s_per_km"] - last_five["pace_s_per_km"], 1)

    last_two_gain = None
    if last_two and previous_two and last_two.get("pace_s_per_km") is not None and previous_two.get("pace_s_per_km") is not None:
        last_two_gain = round(previous_two["pace_s_per_km"] - last_two["pace_s_per_km"], 1)

    signature = None
    if last_five_gain is not None:
        if last_five_gain >= 60:
            signature = "strong_finish"
        elif last_five_gain <= -60:
            signature = "degraded_finish"
        else:
            signature = "neutral_finish"

    return {
        "eligible": True,
        "full_km_lap_count": len(full_km_laps),
        "last_5k": last_five,
        "previous_5k": previous_five,
        "last_5k_gain_s_per_km": last_five_gain,
        "last_2k": last_two,
        "previous_2k": previous_two,
        "last_2k_gain_s_per_km": last_two_gain,
        "final_attack_signature": signature,
        "fastest_last_3_full_km_laps": sorted(full_km_laps[-3:], key=lambda item: item["pace_s_per_km"] or 10**9),
    }


def build_fit_summary(session: dict[str, Any] | None, lap_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if session is None:
        return None
    elapsed_s = float(session.get("total_elapsed_time") or 0.0)
    timer_s = float(session.get("total_timer_time") or 0.0)
    distance_km = (float(session.get("total_distance") or 0.0) / 1000.0) if session.get("total_distance") is not None else None
    ascent_m = int(session.get("total_ascent") or 0)
    avg_hr = session.get("avg_heart_rate")
    pace_moving = (timer_s / distance_km) if distance_km else None
    pace_elapsed = (elapsed_s / distance_km) if distance_km else None
    vertical_per_km = (ascent_m / distance_km) if distance_km else None
    vertical_speed_elapsed = (ascent_m / (elapsed_s / 3600.0)) if elapsed_s else None
    vertical_speed_moving = (ascent_m / (timer_s / 3600.0)) if timer_s else None
    mountain_index = (distance_km + ascent_m / 100.0) if distance_km is not None else None
    heart_rate_efficiency = (pace_moving / avg_hr) if pace_moving is not None and avg_hr else None
    full_km_lap_count = sum(1 for item in lap_items if item["distance_km"] > 0.95)

    return {
        "sport": session.get("sport"),
        "sub_sport": session.get("sub_sport"),
        "sport_profile_name": session.get("sport_profile_name"),
        "total_distance_km": round_or_none(distance_km, 3),
        "total_elapsed_time_s": round_or_none(elapsed_s, 3),
        "total_timer_time_s": round_or_none(timer_s, 3),
        "stopped_time_s": round_or_none(elapsed_s - timer_s if elapsed_s and timer_s else None, 3),
        "total_ascent_m": ascent_m,
        "total_descent_m": int(session.get("total_descent") or 0),
        "avg_hr": avg_hr,
        "max_hr": session.get("max_heart_rate"),
        "total_calories": session.get("total_calories"),
        "total_strides": session.get("total_strides"),
        "avg_running_cadence": session.get("avg_running_cadence"),
        "max_running_cadence": session.get("max_running_cadence"),
        "avg_speed_kmh": round_or_none((float(session.get("enhanced_avg_speed") or 0.0) * 3.6) if session.get("enhanced_avg_speed") is not None else None, 2),
        "max_speed_kmh": round_or_none((float(session.get("enhanced_max_speed") or 0.0) * 3.6) if session.get("enhanced_max_speed") is not None else None, 2),
        "min_altitude_m": round_or_none(float(session.get("enhanced_min_altitude")) if session.get("enhanced_min_altitude") is not None else None, 1),
        "max_altitude_m": round_or_none(float(session.get("enhanced_max_altitude")) if session.get("enhanced_max_altitude") is not None else None, 1),
        "avg_power": session.get("avg_power"),
        "max_power": session.get("max_power"),
        "normalized_power": session.get("normalized_power"),
        "total_training_effect": session.get("total_training_effect"),
        "total_anaerobic_training_effect": session.get("total_anaerobic_training_effect"),
        "lap_count": len(lap_items),
        "full_km_lap_count": full_km_lap_count,
        "pace_moving_s_per_km": round_or_none(pace_moving, 2),
        "pace_moving_avg": fmt_pace(pace_moving),
        "pace_elapsed_s_per_km": round_or_none(pace_elapsed, 2),
        "pace_elapsed_avg": fmt_pace(pace_elapsed),
        "vertical_per_km": round_or_none(vertical_per_km, 2),
        "vertical_speed_elapsed_m_per_h": round_or_none(vertical_speed_elapsed, 1),
        "vertical_speed_moving_m_per_h": round_or_none(vertical_speed_moving, 1),
        "mountain_index": round_or_none(mountain_index, 2),
        "heart_rate_efficiency": round_or_none(heart_rate_efficiency, 3),
    }


def build_deltas(activity: dict[str, Any], fit_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if fit_summary is None:
        return None
    strava_distance = safe_float(activity.get("distance_km"))
    strava_elapsed = parse_duration_to_seconds(activity.get("elapsed_time")) or activity.get("elapsed_time_seconds")
    strava_moving = parse_duration_to_seconds(activity.get("moving_time")) or activity.get("moving_time_seconds")
    strava_ascent = safe_float(activity.get("elevation_gain_m"))
    strava_avg_hr = safe_float(activity.get("avg_hr"))
    strava_max_hr = safe_float(activity.get("max_hr"))
    strava_calories = safe_float(activity.get("calories"))

    return {
        "distance_delta_km": round_or_none((fit_summary.get("total_distance_km") - strava_distance) if fit_summary.get("total_distance_km") is not None and strava_distance is not None else None, 3),
        "elapsed_time_delta_s": round_or_none((fit_summary.get("total_elapsed_time_s") - float(strava_elapsed)) if fit_summary.get("total_elapsed_time_s") is not None and strava_elapsed is not None else None, 1),
        "moving_time_delta_s": round_or_none((fit_summary.get("total_timer_time_s") - float(strava_moving)) if fit_summary.get("total_timer_time_s") is not None and strava_moving is not None else None, 1),
        "ascent_delta_m": round_or_none((fit_summary.get("total_ascent_m") - strava_ascent) if fit_summary.get("total_ascent_m") is not None and strava_ascent is not None else None, 1),
        "avg_hr_delta": round_or_none((fit_summary.get("avg_hr") - strava_avg_hr) if fit_summary.get("avg_hr") is not None and strava_avg_hr is not None else None, 1),
        "max_hr_delta": round_or_none((fit_summary.get("max_hr") - strava_max_hr) if fit_summary.get("max_hr") is not None and strava_max_hr is not None else None, 1),
        "calories_delta": round_or_none((fit_summary.get("total_calories") - strava_calories) if fit_summary.get("total_calories") is not None and strava_calories is not None else None, 1),
    }


def aggregate_overview(entries: list[dict[str, Any]], failures: list[dict[str, Any]], total_index_count: int) -> dict[str, Any]:
    parsed = [entry for entry in entries if entry["fit_status"] == "parsed"]
    missing_raw = [entry for entry in entries if entry["fit_status"] == "missing_raw"]
    parse_error = [entry for entry in entries if entry["fit_status"] == "parse_error"]
    by_type = Counter(entry.get("activity_type") or "unknown" for entry in parsed)
    parsed_runs = [entry for entry in parsed if entry.get("activity_type") == "Run"]
    parsed_races = [entry for entry in parsed if entry.get("is_race_candidate")]
    run_finish_signatures = Counter(
        entry.get("finish_analysis", {}).get("final_attack_signature")
        for entry in parsed_runs
        if entry.get("finish_analysis") and entry.get("finish_analysis", {}).get("final_attack_signature")
    )
    race_finish_signatures = Counter(
        entry.get("finish_analysis", {}).get("final_attack_signature")
        for entry in parsed_races
        if entry.get("finish_analysis") and entry.get("finish_analysis", {}).get("final_attack_signature")
    )

    def best_of(key: str, label: str) -> dict[str, Any] | None:
        candidates = [entry for entry in parsed_runs if entry.get("fit_summary", {}).get(key) is not None]
        if not candidates:
            return None
        best = max(candidates, key=lambda entry: entry["fit_summary"][key])
        return {
            "label": label,
            "date": best.get("date"),
            "name": best.get("name"),
            "value": best["fit_summary"][key],
        }

    hr_coverage = sum(1 for entry in parsed_runs if entry.get("fit_summary", {}).get("avg_hr") is not None)
    stopped_seconds = [entry.get("fit_summary", {}).get("stopped_time_s") for entry in parsed_runs if entry.get("fit_summary", {}).get("stopped_time_s") is not None]

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_index_activities": total_index_count,
        "fit_linked_entries": len([entry for entry in entries if entry.get("filename")]),
        "fit_parsed_entries": len(parsed),
        "entries_missing_raw_file": len(missing_raw),
        "entries_with_non_fit_raw_file": len([entry for entry in entries if entry["fit_status"] == "non_fit_raw"]),
        "fit_parse_error_entries": len(parse_error),
        "parse_failures_logged": len(failures),
        "parsed_by_activity_type": dict(sorted(by_type.items())),
        "run_fit_coverage": {
            "parsed_run_entries": len(parsed_runs),
            "run_entries_with_avg_hr": hr_coverage,
            "total_run_distance_km": round(sum(entry["fit_summary"].get("total_distance_km") or 0.0 for entry in parsed_runs), 1),
            "total_run_ascent_m": round(sum(entry["fit_summary"].get("total_ascent_m") or 0.0 for entry in parsed_runs), 1),
            "average_stopped_time_s": round(mean(stopped_seconds), 1) if stopped_seconds else None,
            "finish_signatures": dict(sorted(run_finish_signatures.items())),
        },
        "race_fit_coverage": {
            "parsed_race_like_entries": len(parsed_races),
            "finish_signatures": dict(sorted(race_finish_signatures.items())),
        },
        "fit_benchmarks": {
            "longest_run": best_of("total_distance_km", "Longest run by FIT"),
            "biggest_climb_run": best_of("total_ascent_m", "Biggest climb run by FIT"),
            "highest_vertical_density_run": best_of("vertical_per_km", "Highest vertical density run by FIT"),
        },
    }


def build_markdown(overview: dict[str, Any], failures: list[dict[str, Any]]) -> str:
    lines = [
        "# FIT Statistical Base",
        "",
        f"Gerado em: {overview['generated_at']}",
        "",
        "## Cobertura",
        f"- Atividades no indice normalizado: {overview['total_index_activities']}",
        f"- Entradas com arquivo bruto associado: {overview['fit_linked_entries']}",
        f"- FITs parseados com sucesso: {overview['fit_parsed_entries']}",
        f"- Entradas sem arquivo bruto: {overview['entries_missing_raw_file']}",
        f"- Entradas com bruto nao-FIT: {overview['entries_with_non_fit_raw_file']}",
        f"- Entradas com erro de parse FIT: {overview['fit_parse_error_entries']}",
        "",
        "## Cobertura de corrida",
        f"- Corridas parseadas por FIT: {overview['run_fit_coverage']['parsed_run_entries']}",
        f"- Corridas com FC media vinda do FIT: {overview['run_fit_coverage']['run_entries_with_avg_hr']}",
        f"- Distancia total de corrida por FIT: {overview['run_fit_coverage']['total_run_distance_km']} km",
        f"- D+ total de corrida por FIT: {overview['run_fit_coverage']['total_run_ascent_m']} m",
        f"- Tempo parado medio em corridas com FIT: {overview['run_fit_coverage']['average_stopped_time_s']} s",
        "",
        "## Assinaturas de fechamento em corridas",
    ]
    run_signatures = overview['run_fit_coverage']['finish_signatures']
    if run_signatures:
        for key, value in run_signatures.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- Nenhuma assinatura de fechamento elegivel foi encontrada.")

    lines.extend(["", "## Assinaturas de fechamento em provas"])
    race_signatures = overview['race_fit_coverage']['finish_signatures']
    if race_signatures:
        for key, value in race_signatures.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- Nenhuma assinatura de fechamento elegivel foi encontrada nas provas.")

    lines.extend(["", "## Benchmarks FIT"])
    for key in ("longest_run", "biggest_climb_run", "highest_vertical_density_run"):
        item = overview['fit_benchmarks'].get(key)
        if item:
            lines.append(f"- {item['label']}: {item['name']} em {item['date']} com valor {item['value']}")

    if failures:
        lines.extend(["", "## Erros de parse", f"- Total de falhas registradas: {len(failures)}"])
        for item in failures[:10]:
            lines.append(f"- {item['filename']}: {item['error']}")

    lines.extend([
        "",
        "## Uso recomendado",
        "- Priorizar a base FIT para distancia, tempo em movimento, tempo parado, FC, laps e leitura de fechamento quando houver arquivo bruto.",
        "- Continuar priorizando GPX oficial para altimetria de prova quando ele existir, porque o FIT segue sendo altimetria de relogio.",
        "- Usar o indice enriquecido para futuras analises de treino e prova com menos dependencia do resumo simplificado do Strava.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a FIT-derived statistical base for all indexed activities.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    data_dir = project_root / "data"
    analysis_context_dir = project_root / "analysis" / "context"
    activities_dir = project_root / "activities" / "strava_export"

    index_path = data_dir / "strava_activities_index.json"
    activities = load_json(index_path)
    if not isinstance(activities, list):
        raise ValueError("strava_activities_index.json precisa conter uma lista.")

    entries: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for activity in activities:
        filename = activity.get("filename")
        entry = {
            "activity_id": activity.get("activity_id"),
            "date": activity.get("date"),
            "date_time": activity.get("date_time"),
            "name": activity.get("name"),
            "activity_type": activity.get("activity_type"),
            "subtype": activity.get("subtype"),
            "classification_hint": activity.get("classification_hint"),
            "is_race_candidate": activity.get("is_race_candidate"),
            "filename": filename,
            "fit_status": None,
            "fit_summary": None,
            "fit_vs_strava": None,
            "finish_analysis": None,
        }

        if not filename:
            entry["fit_status"] = "missing_raw"
            entries.append(entry)
            continue

        fit_path = activities_dir / Path(filename)
        if not fit_path.exists():
            alt_path = project_root / filename
            fit_path = alt_path if alt_path.exists() else fit_path
        if not fit_path.exists():
            entry["fit_status"] = "missing_raw"
            entries.append(entry)
            continue

        suffixes = [part.lower() for part in fit_path.suffixes]
        if ".fit" not in suffixes:
            entry["fit_status"] = "non_fit_raw"
            entries.append(entry)
            continue

        try:
            session, laps = parse_fit_file(fit_path)
            lap_items = summarize_laps(laps)
            fit_summary = build_fit_summary(session, lap_items)
            finish_analysis = build_finish_analysis(lap_items, str(activity.get("activity_type") or ""))
            entry["fit_status"] = "parsed" if fit_summary is not None else "parse_error"
            entry["fit_summary"] = fit_summary
            entry["fit_vs_strava"] = build_deltas(activity, fit_summary)
            entry["finish_analysis"] = finish_analysis
            if fit_summary is None:
                failures.append({"filename": str(fit_path), "error": "session message not found"})
        except Exception as exc:  # noqa: BLE001
            entry["fit_status"] = "parse_error"
            failures.append({"filename": str(fit_path), "error": str(exc)})

        entries.append(entry)

    overview = aggregate_overview(entries, failures, len(activities))

    fit_stats_path = data_dir / "fit_activity_statistics.json"
    fit_overview_path = data_dir / "fit_statistics_overview.json"
    fit_failures_path = data_dir / "fit_parse_failures.json"
    fit_master_index_path = data_dir / "activity_master_index.json"
    fit_md_path = analysis_context_dir / "fit_statistics_base.md"

    save_json(entries, fit_stats_path)
    save_json(overview, fit_overview_path)
    save_json(failures, fit_failures_path)

    # Merge the original normalized activity row with FIT-derived data to create the new master index.
    master_index = []
    for activity, fit_entry in zip(activities, entries):
        merged = dict(activity)
        merged["fit_status"] = fit_entry["fit_status"]
        merged["fit_summary"] = fit_entry["fit_summary"]
        merged["fit_vs_strava"] = fit_entry["fit_vs_strava"]
        merged["finish_analysis"] = fit_entry["finish_analysis"]
        master_index.append(merged)
    save_json(master_index, fit_master_index_path)

    fit_md_path.parent.mkdir(parents=True, exist_ok=True)
    fit_md_path.write_text(build_markdown(overview, failures), encoding="utf-8")

    print(fit_stats_path)
    print(fit_overview_path)
    print(fit_failures_path)
    print(fit_master_index_path)
    print(fit_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
