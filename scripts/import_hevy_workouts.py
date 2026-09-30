from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANALYSIS_DIR = ROOT / "analysis" / "context"
DEFAULT_INPUT = ROOT / "activities" / "hevy" / "workouts.csv"
DEFAULT_API_INPUT = DATA_DIR / "hevy_api_exports" / "hevy_workouts_latest.json"
HEVY_OUT = DATA_DIR / "hevy_workouts.json"
CONSOLIDATED_OUT = DATA_DIR / "strength_training_consolidated.json"
TRAINING_HISTORY = DATA_DIR / "training_history.json"
REPORT_OUT = ANALYSIS_DIR / "hevy_garmin_strength_import.md"

MONTHS = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def slug(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "workout"


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def parse_hevy_datetime(value: str) -> datetime:
    text = strip_accents(value.strip().lower()).replace(".", "")
    match = re.match(r"(\d{1,2}) de ([a-z]{3}) de (\d{4}), (\d{1,2}):(\d{2})", text)
    if not match:
        raise ValueError(f"Unsupported Hevy datetime: {value}")
    day, month_key, year, hour, minute = match.groups()
    month = MONTHS[month_key]
    return datetime(int(year), month, int(day), int(hour), int(minute))


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def parse_hevy_api_datetime(value: Any) -> datetime:
    if not value:
        raise ValueError("Hevy API workout is missing a timestamp")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    return parsed


def seconds_to_hms(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def classify_title(title: str) -> str:
    normalized = strip_accents(title).lower()
    if "pull" in normalized or "costa" in normalized or "biceps" in normalized:
        return "pull"
    if "push" in normalized or "peito" in normalized or "triceps" in normalized or "ombro" in normalized:
        return "push"
    if "perna" in normalized or "leg" in normalized:
        return "legs"
    if "core" in normalized or "estabil" in normalized:
        return "core"
    return "strength"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_sessions(rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["title"], row["start_time"], row["end_time"])].append(row)

    sessions: list[dict[str, Any]] = []
    for (title, start_raw, end_raw), items in grouped.items():
        start = parse_hevy_datetime(start_raw)
        end = parse_hevy_datetime(end_raw)
        duration_seconds = max(0, int((end - start).total_seconds()))
        exercises_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        total_volume = 0.0
        total_reps = 0
        total_sets = 0
        working_sets = 0
        rpe_values: list[float] = []

        for row in items:
            exercise = row["exercise_title"].strip()
            weight = parse_float(row.get("weight_kg"))
            reps = parse_int(row.get("reps"))
            distance = parse_float(row.get("distance_km"))
            duration = parse_int(row.get("duration_seconds"))
            rpe = parse_float(row.get("rpe"))
            set_type = row.get("set_type", "").strip() or "normal"
            set_data = {
                "set_index": parse_int(row.get("set_index")),
                "set_type": set_type,
                "weight_kg": weight,
                "reps": reps,
                "distance_km": distance,
                "duration_seconds": duration,
                "rpe": rpe,
                "superset_id": row.get("superset_id") or None,
                "notes": row.get("exercise_notes") or None,
            }
            exercises_by_name[exercise].append(set_data)
            total_sets += 1
            if set_type.lower() != "warmup":
                working_sets += 1
            if reps:
                total_reps += reps
            if weight is not None and reps is not None:
                total_volume += weight * reps
            if rpe is not None:
                rpe_values.append(rpe)

        exercises: list[dict[str, Any]] = []
        for exercise_name, sets in exercises_by_name.items():
            exercise_volume = 0.0
            exercise_reps = 0
            weights = []
            for set_data in sets:
                weight = set_data.get("weight_kg")
                reps = set_data.get("reps")
                if reps:
                    exercise_reps += reps
                if weight is not None:
                    weights.append(weight)
                if weight is not None and reps is not None:
                    exercise_volume += weight * reps
            exercises.append(
                {
                    "name": exercise_name,
                    "sets": sets,
                    "set_count": len(sets),
                    "total_reps": exercise_reps,
                    "volume_kg": round(exercise_volume, 1),
                    "max_weight_kg": max(weights) if weights else None,
                }
            )

        session_id = f"hevy_{start.strftime('%Y%m%d_%H%M')}_{slug(title)}"
        sessions.append(
            {
                "hevy_workout_id": session_id,
                "source": "hevy_csv",
                "source_file": str(source_path),
                "title": title,
                "classification": classify_title(title),
                "date": start.date().isoformat(),
                "start_time": start.isoformat(timespec="minutes"),
                "end_time": end.isoformat(timespec="minutes"),
                "duration_seconds": duration_seconds,
                "duration": seconds_to_hms(duration_seconds),
                "description": items[0].get("description") or None,
                "exercise_count": len(exercises),
                "total_sets": total_sets,
                "working_sets": working_sets,
                "total_reps": total_reps,
                "total_volume_kg": round(total_volume, 1),
                "avg_rpe": round(sum(rpe_values) / len(rpe_values), 1) if rpe_values else None,
                "exercises_preview": [exercise["name"] for exercise in exercises[:8]],
                "exercises": exercises,
            }
        )

    return sorted(sessions, key=lambda item: item["start_time"])


def read_api_workouts(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        workouts = payload
    elif isinstance(payload, dict):
        workouts = payload.get("workouts")
    else:
        workouts = None
    if not isinstance(workouts, list):
        raise ValueError(f"Hevy API JSON does not contain a workouts list: {path}")
    return [item for item in workouts if isinstance(item, dict)]


def build_api_sessions(workouts: list[dict[str, Any]], source_path: Path) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for workout in workouts:
        start = parse_hevy_api_datetime(workout.get("start_time"))
        end = parse_hevy_api_datetime(workout.get("end_time"))
        duration_seconds = max(0, int((end - start).total_seconds()))
        exercises: list[dict[str, Any]] = []
        total_sets = 0
        working_sets = 0
        total_reps = 0
        total_volume = 0.0
        rpe_values: list[float] = []

        raw_exercises = workout.get("exercises") or []
        for raw_exercise in raw_exercises:
            if not isinstance(raw_exercise, dict):
                continue
            sets: list[dict[str, Any]] = []
            exercise_reps = 0
            exercise_volume = 0.0
            weights: list[float] = []
            for raw_set in raw_exercise.get("sets") or []:
                if not isinstance(raw_set, dict):
                    continue
                set_type = str(raw_set.get("type") or "normal")
                weight = parse_float(raw_set.get("weight_kg"))
                reps = parse_int(raw_set.get("reps"))
                distance_meters = parse_float(raw_set.get("distance_meters"))
                duration = parse_int(raw_set.get("duration_seconds"))
                rpe = parse_float(raw_set.get("rpe"))
                set_data = {
                    "set_index": parse_int(raw_set.get("index")),
                    "set_type": set_type,
                    "weight_kg": weight,
                    "reps": reps,
                    "distance_km": round(distance_meters / 1000.0, 3) if distance_meters is not None else None,
                    "duration_seconds": duration,
                    "rpe": rpe,
                    "custom_metric": parse_float(raw_set.get("custom_metric")),
                    "superset_id": raw_exercise.get("supersets_id"),
                    "notes": raw_exercise.get("notes") or None,
                }
                sets.append(set_data)
                total_sets += 1
                if set_type.lower() != "warmup":
                    working_sets += 1
                if reps is not None:
                    total_reps += reps
                    exercise_reps += reps
                if weight is not None:
                    weights.append(weight)
                if weight is not None and reps is not None:
                    set_volume = weight * reps
                    total_volume += set_volume
                    exercise_volume += set_volume
                if rpe is not None:
                    rpe_values.append(rpe)

            exercises.append(
                {
                    "name": str(raw_exercise.get("title") or "Exercise"),
                    "exercise_template_id": raw_exercise.get("exercise_template_id"),
                    "sets": sets,
                    "set_count": len(sets),
                    "total_reps": exercise_reps,
                    "volume_kg": round(exercise_volume, 1),
                    "max_weight_kg": max(weights) if weights else None,
                }
            )

        title = str(workout.get("title") or "Hevy strength workout")
        workout_id = str(workout.get("id") or f"hevy_{start.strftime('%Y%m%d_%H%M')}_{slug(title)}")
        sessions.append(
            {
                "hevy_workout_id": workout_id,
                "source": "hevy_api",
                "source_file": str(source_path),
                "title": title,
                "classification": classify_title(title),
                "date": start.date().isoformat(),
                "start_time": start.isoformat(timespec="minutes"),
                "end_time": end.isoformat(timespec="minutes"),
                "start_time_api": workout.get("start_time"),
                "end_time_api": workout.get("end_time"),
                "updated_at": workout.get("updated_at"),
                "created_at": workout.get("created_at"),
                "routine_id": workout.get("routine_id"),
                "duration_seconds": duration_seconds,
                "duration": seconds_to_hms(duration_seconds),
                "description": workout.get("description") or None,
                "exercise_count": len(exercises),
                "total_sets": total_sets,
                "working_sets": working_sets,
                "total_reps": total_reps,
                "total_volume_kg": round(total_volume, 1),
                "avg_rpe": round(sum(rpe_values) / len(rpe_values), 1) if rpe_values else None,
                "exercises_preview": [exercise["name"] for exercise in exercises[:8]],
                "exercises": exercises,
            }
        )

    deduplicated = {session["hevy_workout_id"]: session for session in sessions}
    return sorted(deduplicated.values(), key=lambda item: item["start_time"])


def build_garmin_strength_index(training_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(training_history):
        if item.get("type") != "Weight Training":
            continue
        start = parse_iso_datetime(item.get("date_time"))
        rows.append({"index": index, "item": item, "start": start})
    return rows


def deduplicate_legacy_strength(training_history: list[dict[str, Any]]) -> int:
    """Fold date-only legacy exports into an equivalent timed Garmin record."""
    removed: set[int] = set()
    for index, legacy in enumerate(training_history):
        if legacy.get("type") != "Weight Training" or legacy.get("date_time"):
            continue
        try:
            seconds = sum(int(value) * factor for value, factor in zip(str(legacy.get("elapsed_time")).split(":"), (3600, 60, 1)))
        except ValueError:
            continue
        if legacy.get("avg_hr") is None or len(str(legacy.get("elapsed_time")).split(":")) != 3:
            continue
        matches = []
        for candidate in training_history:
            if candidate is legacy or candidate.get("type") != "Weight Training" or candidate.get("date") != legacy.get("date") or not candidate.get("date_time"):
                continue
            if candidate.get("avg_hr") is None or len(str(candidate.get("elapsed_time")).split(":")) != 3:
                continue
            try:
                other_seconds = sum(int(value) * factor for value, factor in zip(str(candidate.get("elapsed_time")).split(":"), (3600, 60, 1)))
            except ValueError:
                continue
            if abs(seconds - other_seconds) <= 2 and abs(float(legacy["avg_hr"]) - float(candidate["avg_hr"])) <= 2:
                matches.append(candidate)
        if len(matches) != 1:
            continue
        canonical = matches[0]
        for field in ("relative_effort", "training_load"):
            if canonical.get(field) is None and legacy.get(field) is not None:
                canonical[field] = legacy[field]
        sources = [part for part in (str(canonical.get("source") or "") + "+" + str(legacy.get("source") or "")).split("+") if part]
        canonical["source"] = "+".join(dict.fromkeys(sources))
        removed.add(index)
    training_history[:] = [row for index, row in enumerate(training_history) if index not in removed]
    return len(removed)


def consolidate_strength_days(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    result = []
    for day, sessions in sorted(by_day.items()):
        if len(sessions) == 1:
            result.append(sessions[0])
            continue
        hevy = [row for row in sessions if row.get("hevy_workout_id")]
        primary = dict(hevy[0] if hevy else sessions[0])
        garmin = [row for row in sessions if row.get("garmin_start_time") or row.get("garmin_activity_id")]
        def duration_seconds(value: str | None) -> int:
            try:
                hours, minutes, seconds = map(int, str(value).split(":"))
                return hours * 3600 + minutes * 60 + seconds
            except (TypeError, ValueError):
                return 0
        total_seconds = sum(duration_seconds(row.get("garmin_elapsed_time")) for row in garmin)
        weighted_hr = sum(duration_seconds(row.get("garmin_elapsed_time")) * float(row["garmin_avg_hr"]) for row in garmin if row.get("garmin_avg_hr") is not None)
        measured_seconds = sum(duration_seconds(row.get("garmin_elapsed_time")) for row in garmin if row.get("garmin_avg_hr") is not None)
        if total_seconds:
            primary["garmin_elapsed_time"] = seconds_to_hms(total_seconds)
        if measured_seconds:
            primary["garmin_avg_hr"] = round(weighted_hr / measured_seconds)
        maximums = [row["garmin_max_hr"] for row in garmin if row.get("garmin_max_hr") is not None]
        if maximums:
            primary["garmin_max_hr"] = max(maximums)
        for field in ("hevy_exercise_count", "hevy_total_sets", "hevy_working_sets", "hevy_total_reps", "hevy_total_volume_kg"):
            values = [row[field] for row in hevy if row.get(field) is not None]
            if values:
                primary[field] = round(sum(values), 1) if field == "hevy_total_volume_kg" else sum(values)
        primary["hevy_workout_ids"] = [row["hevy_workout_id"] for row in hevy]
        primary["garmin_activity_ids"] = [row["garmin_activity_id"] for row in garmin if row.get("garmin_activity_id")]
        primary["source_sessions"] = sessions
        result.append(primary)
    return result


def match_sessions(
    sessions: list[dict[str, Any]],
    training_history: list[dict[str, Any]],
    tolerance_minutes: int,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    garmin_rows = build_garmin_strength_index(training_history)
    used_garmin_indexes: set[int] = set()
    enriched_by_index: dict[int, dict[str, Any]] = {}
    consolidated: list[dict[str, Any]] = []

    for session in sessions:
        hevy_start = datetime.fromisoformat(session["start_time"])
        candidates = []
        for row in garmin_rows:
            if row["index"] in used_garmin_indexes:
                continue
            item = row["item"]
            if item.get("date") != session["date"]:
                continue
            garmin_start = row["start"]
            if garmin_start is None:
                # Older Strava/Garmin-enriched strength rows may only have a date.
                # If the day matches and there is no timestamp, treat it as a date-level match.
                delta_minutes = 0.0
            else:
                delta_minutes = abs((garmin_start - hevy_start).total_seconds()) / 60.0
            candidates.append((delta_minutes, row))
        candidates.sort(key=lambda pair: (pair[1]["start"] is None, pair[0]))

        match_row = candidates[0][1] if candidates and candidates[0][0] <= tolerance_minutes else None
        match_delta = round(candidates[0][0], 1) if candidates else None
        match_status = "matched" if match_row else "unmatched_hevy"
        garmin_item = match_row["item"] if match_row else None

        if match_row:
            used_garmin_indexes.add(match_row["index"])
            enriched_by_index[match_row["index"]] = session

        consolidated.append(
            {
                "date": session["date"],
                "hevy_workout_id": session["hevy_workout_id"],
                "hevy_source": session.get("source"),
                "hevy_title": session["title"],
                "classification": session["classification"],
                "hevy_start_time": session["start_time"],
                "hevy_end_time": session["end_time"],
                "hevy_duration": session["duration"],
                "hevy_exercise_count": session["exercise_count"],
                "hevy_total_sets": session["total_sets"],
                "hevy_working_sets": session["working_sets"],
                "hevy_total_reps": session["total_reps"],
                "hevy_total_volume_kg": session["total_volume_kg"],
                "hevy_exercises_preview": session["exercises_preview"],
                "garmin_match_status": match_status,
                "garmin_match_delta_minutes": match_delta if match_row else None,
                "garmin_activity_id": garmin_item.get("garmin_activity_id") if garmin_item else None,
                "garmin_start_time": garmin_item.get("date_time") if garmin_item else None,
                "garmin_elapsed_time": garmin_item.get("elapsed_time") if garmin_item else None,
                "garmin_avg_hr": garmin_item.get("avg_hr") if garmin_item else None,
                "garmin_max_hr": garmin_item.get("max_hr") if garmin_item else None,
            }
        )

    for row in garmin_rows:
        if row["index"] in used_garmin_indexes:
            continue
        item = row["item"]
        consolidated.append(
            {
                "date": item.get("date"),
                "hevy_workout_id": None,
                "hevy_source": None,
                "hevy_title": None,
                "classification": "garmin_only_strength",
                "hevy_start_time": None,
                "hevy_end_time": None,
                "hevy_duration": None,
                "hevy_exercise_count": None,
                "hevy_total_sets": None,
                "hevy_working_sets": None,
                "hevy_total_reps": None,
                "hevy_total_volume_kg": None,
                "hevy_exercises_preview": [],
                "garmin_match_status": "garmin_only",
                "garmin_match_delta_minutes": None,
                "garmin_activity_id": item.get("garmin_activity_id"),
                "garmin_start_time": item.get("date_time"),
                "garmin_elapsed_time": item.get("elapsed_time"),
                "garmin_avg_hr": item.get("avg_hr"),
                "garmin_max_hr": item.get("max_hr"),
            }
        )

    consolidated.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("hevy_start_time") or item.get("garmin_start_time") or "")))
    return consolidate_strength_days(consolidated), enriched_by_index


HEVY_ENRICHMENT_FIELDS = {
    "hevy_workout_id",
    "hevy_title",
    "hevy_classification",
    "hevy_start_time",
    "hevy_end_time",
    "hevy_duration",
    "hevy_exercise_count",
    "hevy_total_sets",
    "hevy_working_sets",
    "hevy_total_reps",
    "hevy_total_volume_kg",
    "hevy_exercises_preview",
    "strength_detail_source",
}


def clear_hevy_enrichment(training_history: list[dict[str, Any]]) -> None:
    for item in training_history:
        if item.get("type") != "Weight Training":
            continue
        for field in HEVY_ENRICHMENT_FIELDS:
            item.pop(field, None)
        source_parts = [
            part for part in str(item.get("source") or "").split("+") if part not in {"hevy_csv", "hevy_api"}
        ]
        item["source"] = "+".join(source_parts)


def enrich_training_history(training_history: list[dict[str, Any]], enriched_by_index: dict[int, dict[str, Any]]) -> int:
    for index, session in enriched_by_index.items():
        item = training_history[index]
        sources = str(item.get("source") or "")
        source_name = str(session.get("source") or "hevy_api")
        if source_name not in sources.split("+"):
            item["source"] = f"{sources}+{source_name}" if sources else source_name
        item["hevy_workout_id"] = session["hevy_workout_id"]
        item["hevy_title"] = session["title"]
        item["hevy_classification"] = session["classification"]
        item["hevy_start_time"] = session["start_time"]
        item["hevy_end_time"] = session["end_time"]
        item["hevy_duration"] = session["duration"]
        item["hevy_exercise_count"] = session["exercise_count"]
        item["hevy_total_sets"] = session["total_sets"]
        item["hevy_working_sets"] = session["working_sets"]
        item["hevy_total_reps"] = session["total_reps"]
        item["hevy_total_volume_kg"] = session["total_volume_kg"]
        item["hevy_exercises_preview"] = session["exercises_preview"]
        item["strength_detail_source"] = source_name
    return len(enriched_by_index)


def write_report(
    path: Path,
    source_path: Path,
    sessions: list[dict[str, Any]],
    consolidated: list[dict[str, Any]],
    enriched_count: int,
) -> None:
    matched = [row for row in consolidated if row.get("garmin_match_status") == "matched"]
    unmatched = [row for row in consolidated if row.get("garmin_match_status") == "unmatched_hevy"]
    garmin_only = [row for row in consolidated if row.get("garmin_match_status") == "garmin_only"]
    class_counts = Counter(session["classification"] for session in sessions)
    total_volume = round(sum(float(session.get("total_volume_kg") or 0) for session in sessions), 1)
    lines = [
        "# Importação Hevy + Garmin - Treinos de força",
        "",
        f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## Fonte",
        "",
        f"- Fonte Hevy: {source_path}",
        "",
        "## Resumo",
        "",
        f"- Sessões Hevy importadas: {len(sessions)}",
        f"- Sessões Hevy casadas com Garmin: {len(matched)}",
        f"- Sessões Hevy ainda sem Garmin correspondente: {len(unmatched)}",
        f"- Atividades Garmin de força sem Hevy correspondente: {len(garmin_only)}",
        f"- Atividades Garmin enriquecidas em training_history.json: {enriched_count}",
        f"- Volume total Hevy: {total_volume:,.1f} kg".replace(",", "X").replace(".", ",").replace("X", "."),
        "",
        "## Sessões por tipo",
        "",
    ]
    for classification, count in sorted(class_counts.items()):
        lines.append(f"- {classification}: {count}")

    lines += [
        "",
        "## Sessões Hevy casadas com Garmin",
        "",
        "| Data | Hevy | Início Hevy | Garmin | Delta | Séries | Exercícios | Volume |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in matched[-30:]:
        volume = row.get("hevy_total_volume_kg")
        volume_text = "" if volume is None else f"{float(volume):,.1f} kg".replace(",", "X").replace(".", ",").replace("X", ".")
        lines.append(
            f"| {row.get('date')} | {row.get('hevy_title')} | {str(row.get('hevy_start_time'))[11:16]} | "
            f"{row.get('garmin_activity_id')} | {row.get('garmin_match_delta_minutes')} min | "
            f"{row.get('hevy_total_sets')} | {row.get('hevy_exercise_count')} | {volume_text} |"
        )

    if unmatched:
        lines += [
            "",
            "## Sessões Hevy sem Garmin correspondente",
            "",
        ]
        for row in unmatched:
            lines.append(
                f"- {row.get('date')} {str(row.get('hevy_start_time'))[11:16]} | {row.get('hevy_title')} | "
                f"{row.get('hevy_total_sets')} séries | {row.get('hevy_total_volume_kg')} kg"
            )

    lines += [
        "",
        "## Arquivos gerados",
        "",
        f"- {HEVY_OUT}",
        f"- {CONSOLIDATED_OUT}",
        "",
        "## Observação",
        "",
        "O Garmin continua sendo a fonte de FC, duração e carga cardiovascular. O Hevy passa a ser a fonte principal para exercícios, séries, repetições e volume de força.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Hevy CSV or API JSON and consolidate with Garmin strength activities.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--format", choices=["auto", "csv", "api"], default="auto")
    parser.add_argument("--match-tolerance-minutes", type=int, default=180)
    parser.add_argument("--no-enrich-training-history", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.input)
    input_format = args.format
    if input_format == "auto":
        input_format = "api" if source_path.suffix.lower() == ".json" else "csv"
    if input_format == "api":
        sessions = build_api_sessions(read_api_workouts(source_path), source_path)
    else:
        sessions = build_sessions(read_csv_rows(source_path), source_path)
    if not sessions and not args.allow_empty:
        raise ValueError("Hevy import contains no workouts; existing enrichment was left unchanged.")
    training_history = json.loads(TRAINING_HISTORY.read_text(encoding="utf-8-sig"))
    deduplicate_legacy_strength(training_history)
    if not args.no_enrich_training_history:
        clear_hevy_enrichment(training_history)
    consolidated, enriched_by_index = match_sessions(sessions, training_history, args.match_tolerance_minutes)
    enriched_count = 0
    if not args.no_enrich_training_history:
        enriched_count = enrich_training_history(training_history, enriched_by_index)
        TRAINING_HISTORY.write_text(json.dumps(training_history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    HEVY_OUT.write_text(json.dumps(sessions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONSOLIDATED_OUT.write_text(json.dumps(consolidated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(REPORT_OUT, source_path, sessions, consolidated, enriched_count)

    print(f"Hevy sessions: {len(sessions)}")
    print(f"Matched with Garmin: {sum(1 for row in consolidated if row.get('garmin_match_status') == 'matched')}")
    print(f"Unmatched Hevy: {sum(1 for row in consolidated if row.get('garmin_match_status') == 'unmatched_hevy')}")
    print(f"Garmin only: {sum(1 for row in consolidated if row.get('garmin_match_status') == 'garmin_only')}")
    print(f"Training history enriched: {enriched_count}")
    print(f"Wrote {HEVY_OUT}")
    print(f"Wrote {CONSOLIDATED_OUT}")
    print(f"Wrote {REPORT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
