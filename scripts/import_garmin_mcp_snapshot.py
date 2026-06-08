from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from common import format_duration, format_pace, safe_float, save_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "garmin_mcp_exports"
TRAINING_HISTORY_PATH = ROOT / "data" / "training_history.json"
SLEEP_PATH = ROOT / "data" / "garmin_sleep_reference_2026_04.json"
REPORT_PATH = ROOT / "analysis" / "context" / "garmin_mcp_import_update.md"


TYPE_MAP = {
    "running": ("Run", "run"),
    "street_running": ("Run", "road run"),
    "trail_running": ("Run", "trail run"),
    "treadmill_running": ("Run", "treadmill run"),
    "cycling": ("Bike", "cycling"),
    "road_biking": ("Bike", "road cycling"),
    "mountain_biking": ("Bike", "mountain biking"),
    "lap_swimming": ("Swim", "pool swim"),
    "swimming": ("Swim", "swim"),
    "walking": ("Walk", "walk"),
    "hiking": ("Hike", "hike"),
    "strength_training": ("Weight Training", "strength workout"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a Garmin MCP snapshot into the local AscentIQ database."
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Snapshot JSON file or directory. Defaults to data/garmin_mcp_exports.",
    )
    parser.add_argument(
        "--history",
        default=str(TRAINING_HISTORY_PATH),
        help="Training history JSON path.",
    )
    parser.add_argument(
        "--sleep-output",
        default=str(SLEEP_PATH),
        help="Sleep reference JSON path.",
    )
    parser.add_argument("--since", help="Only import activities on or after YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing files.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_json(path)
    return data if isinstance(data, list) else []


def snapshot_paths(raw_paths: list[str]) -> list[Path]:
    paths = [Path(item) for item in raw_paths] if raw_paths else [DEFAULT_INPUT]
    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            out.extend(sorted(path.glob("*.json")))
        elif path.exists():
            out.append(path)
    return out


def walk_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        found.append(payload)
        for value in payload.values():
            found.extend(walk_dicts(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(walk_dicts(item))
    return found


def key_lookup(row: dict[str, Any], *keys: str) -> tuple[str | None, Any]:
    normalized = {str(key).lower(): key for key in row}
    for key in keys:
        actual = normalized.get(key.lower())
        if actual is not None:
            return str(actual), row.get(actual)
    return None, None


def nested_activity_type(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("typeKey", "type_key", "key", "displayName", "name"):
            if value.get(key):
                return str(value[key])
    if value:
        return str(value)
    return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=None)
        except ValueError:
            pass
    return None


def seconds_from_any(value: Any) -> int | None:
    parsed = safe_float(value)
    if parsed is not None:
        return int(round(parsed))
    if not value:
        return None
    parts = str(value).strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
    except ValueError:
        return None
    return None


def distance_km(row: dict[str, Any]) -> float | None:
    key, value = key_lookup(
        row,
        "distanceMeters",
        "distanceInMeters",
        "distance_m",
        "distance",
        "distanceKm",
        "distance_km",
    )
    parsed = safe_float(value)
    if parsed is None:
        return None
    if key and ("meter" in key.lower() or key.lower() == "distance_m"):
        return parsed / 1000.0
    return parsed / 1000.0 if parsed > 1000 else parsed


def activity_type(row: dict[str, Any]) -> tuple[str, str]:
    _, raw = key_lookup(row, "activityType", "sportType", "type", "activity_type")
    type_key = nested_activity_type(raw)
    if not type_key:
        return "Activity", "activity"
    normalized = type_key.strip().lower().replace(" ", "_")
    return TYPE_MAP.get(normalized, (type_key, type_key))


def classify_activity(item: dict[str, Any]) -> str:
    activity = item.get("type")
    distance = safe_float(item.get("distance_km")) or 0.0
    ascent = safe_float(item.get("watch_elevation_gain_m")) or 0.0
    moving_seconds = seconds_from_any(item.get("moving_time_seconds") or item.get("moving_time")) or 0
    name = str(item.get("name") or "").lower()
    if activity == "Weight Training":
        return "forca"
    if activity in {"Hike", "Stair-Stepper"}:
        return "subida especifica"
    if activity == "Swim":
        return "recuperacao"
    if activity == "Run" and (ascent >= 300 or "trail" in name or "climb" in name):
        return "subida especifica"
    if activity == "Run" and (distance >= 20 or moving_seconds >= 7200):
        return "longao"
    if activity == "Run" and any(token in name for token in ("threshold", "tempo", "ritmo", "interval")):
        return "limiar"
    if activity in {"Walk", "Bike"}:
        return "base aerobica"
    return "base aerobica"


def looks_like_activity(row: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in row}
    has_start = bool(keys & {"starttimelocal", "starttimegmt", "starttime", "begintimestamp", "activitystarttime"})
    has_duration = bool(keys & {"duration", "movingduration", "elapsedduration", "durationseconds"})
    has_distance = bool(keys & {"distance", "distancemeters", "distanceinmeters", "distancekm"})
    has_name = bool(keys & {"activityname", "name", "title"})
    is_sleep = any("sleep" in key for key in keys)
    return has_start and (has_duration or has_distance) and has_name and not is_sleep


def normalize_activity(row: dict[str, Any]) -> dict[str, Any] | None:
    _, start = key_lookup(row, "startTimeLocal", "startTimeGMT", "startTime", "beginTimestamp", "activityStartTime")
    start_dt = parse_datetime(start)
    if not start_dt:
        return None
    _, name = key_lookup(row, "activityName", "name", "title")
    _, activity_id = key_lookup(row, "activityId", "activity_id", "id")
    t, subtype = activity_type(row)
    dist = distance_km(row)
    _, duration = key_lookup(row, "duration", "elapsedDuration", "durationSeconds")
    _, moving = key_lookup(row, "movingDuration", "movingDurationSeconds", "moving_time")
    elapsed_seconds = seconds_from_any(duration)
    moving_seconds = seconds_from_any(moving) or elapsed_seconds
    if elapsed_seconds and moving_seconds and moving_seconds > elapsed_seconds:
        moving_seconds = elapsed_seconds
    _, avg_hr = key_lookup(row, "averageHR", "averageHeartRate", "avgHr", "avg_hr")
    _, max_hr = key_lookup(row, "maxHR", "maxHeartRate", "maxHr", "max_hr")
    _, ascent = key_lookup(row, "elevationGain", "elevationGainMeters", "ascent", "totalAscent")

    pace_seconds = moving_seconds / dist if moving_seconds and dist else None
    item = {
        "garmin_activity_id": str(activity_id) if activity_id is not None else None,
        "activity_key": f"{start_dt.isoformat()}|{t}|{name or t}|{elapsed_seconds or ''}",
        "date": start_dt.strftime("%Y-%m-%d"),
        "date_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "name": str(name or t),
        "type": t,
        "subtype": subtype,
        "distance_km": round(dist, 2) if dist is not None else 0.0,
        "elapsed_time": format_duration(elapsed_seconds),
        "moving_time": format_duration(moving_seconds),
        "duration_seconds": elapsed_seconds,
        "moving_time_seconds": moving_seconds,
        "stopped_time_seconds": elapsed_seconds - moving_seconds if elapsed_seconds and moving_seconds is not None else None,
        "avg_hr": int(round(safe_float(avg_hr))) if safe_float(avg_hr) is not None else None,
        "max_hr": int(round(safe_float(max_hr))) if safe_float(max_hr) is not None else None,
        "watch_elevation_gain_m": round(safe_float(ascent) or 0.0, 1),
        "pace_avg": format_pace(pace_seconds),
        "pace_seconds_per_km": round(pace_seconds, 2) if pace_seconds else None,
        "source": "garmin_mcp_snapshot",
        "data_confidence": "garmin_mcp_without_raw_fit",
    }
    item["classification_hint"] = classify_activity(item)
    return item


def extract_activities(payloads: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        for row in walk_dicts(payload):
            if not looks_like_activity(row):
                continue
            activity = normalize_activity(row)
            if not activity:
                continue
            key = activity.get("garmin_activity_id") or activity["activity_key"]
            if key in seen:
                continue
            seen.add(key)
            items.append(activity)
    return sorted(items, key=lambda item: item.get("date_time") or "")


def sleep_score(row: dict[str, Any]) -> int | None:
    _, direct = key_lookup(row, "sleepScore", "score", "overallSleepScore")
    parsed = safe_float(direct)
    if parsed is not None:
        return int(round(parsed))
    _, nested = key_lookup(row, "sleepScores")
    if isinstance(nested, dict):
        for key in ("overall", "overallScore", "total", "score"):
            parsed = safe_float(nested.get(key))
            if parsed is not None:
                return int(round(parsed))
    return None


def normalize_sleep(row: dict[str, Any]) -> dict[str, Any] | None:
    _, date_value = key_lookup(row, "calendarDate", "date", "sleepDate")
    if not date_value:
        _, start = key_lookup(row, "sleepStartTimestampLocal", "sleepStartTimestampGMT", "bedTime")
        start_dt = parse_datetime(start)
        date_value = start_dt.strftime("%Y-%m-%d") if start_dt else None
    if not date_value:
        return None
    score = sleep_score(row)
    _, quality = key_lookup(row, "quality", "sleepQuality")
    _, duration = key_lookup(row, "sleepTimeSeconds", "sleepDurationSeconds", "durationSeconds", "duration_minutes")
    duration_seconds = seconds_from_any(duration)
    if duration_seconds and str(duration).isdigit() and int(duration) < 1440:
        duration_seconds = int(duration) * 60
    duration_minutes = int(round(duration_seconds / 60)) if duration_seconds else None
    _, bed = key_lookup(row, "sleepStartTimestampLocal", "bedTime", "sleepStart")
    _, wake = key_lookup(row, "sleepEndTimestampLocal", "wakeTime", "sleepEnd")
    _, resting_hr = key_lookup(row, "restingHeartRate", "resting_hr", "restingHR")
    _, body_battery = key_lookup(row, "bodyBattery", "body_battery")
    _, respiration = key_lookup(row, "respiration", "averageRespiration")
    _, hrv = key_lookup(row, "hrvStatus", "hrv_status", "hrv")
    hours, minutes = divmod(duration_minutes or 0, 60)
    return {
        "date": str(date_value)[:10],
        "score": score,
        "quality": str(quality) if quality else None,
        "duration_raw": f"{hours}h {minutes}min" if duration_minutes is not None else None,
        "bed_time": str(bed) if bed else None,
        "wake_time": str(wake) if wake else None,
        "resting_hr": int(round(safe_float(resting_hr))) if safe_float(resting_hr) is not None else None,
        "body_battery": int(round(safe_float(body_battery))) if safe_float(body_battery) is not None else None,
        "respiration": safe_float(respiration),
        "hrv_status": str(hrv) if hrv is not None else None,
        "duration_minutes": duration_minutes,
    }


def looks_like_sleep(row: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in row}
    return bool(keys & {"sleepscore", "sleepscores", "sleeptimeseconds", "sleepscoreoverall", "overallsleepscore"})


def extract_sleep(payloads: list[Any]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in walk_dicts(payload):
            if not looks_like_sleep(row):
                continue
            item = normalize_sleep(row)
            if item:
                by_date[item["date"]] = item
    return [by_date[day] for day in sorted(by_date)]


def history_key(item: dict[str, Any]) -> tuple[Any, ...]:
    garmin_id = item.get("garmin_activity_id")
    if garmin_id:
        return ("garmin", garmin_id)
    return (
        "fallback",
        item.get("date_time") or item.get("date"),
        item.get("type"),
        item.get("name"),
        item.get("elapsed_time"),
    )


def merge_history(existing: list[dict[str, Any]], new_items: list[dict[str, Any]], since: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys = {history_key(item) for item in existing}
    fallback_keys = {
        (
            "fallback",
            item.get("date_time") or item.get("date"),
            item.get("type"),
            item.get("name"),
            item.get("elapsed_time"),
        )
        for item in existing
    }
    added: list[dict[str, Any]] = []
    merged = [dict(item) for item in existing]
    for item in new_items:
        if since and item.get("date", "") < since:
            continue
        key = history_key(item)
        fallback = ("fallback", item.get("date_time"), item.get("type"), item.get("name"), item.get("elapsed_time"))
        if key in keys or fallback in fallback_keys:
            continue
        merged.append(item)
        added.append(item)
        keys.add(key)
        fallback_keys.add(fallback)
    merged.sort(key=lambda item: item.get("date_time") or item.get("date") or "")
    return merged, added


def merge_sleep(existing_path: Path, new_sleep: list[dict[str, Any]]) -> dict[str, Any]:
    existing = load_json(existing_path) if existing_path.exists() else {"daily": [], "weekly": []}
    by_date = {item.get("date"): item for item in existing.get("daily", []) if item.get("date")}
    for item in new_sleep:
        by_date[item["date"]] = item
    daily = [by_date[day] for day in sorted(by_date)]
    scored = [item for item in daily if item.get("score") is not None]
    latest = scored[-1] if scored else None
    last_7 = scored[-7:]
    avg_score = round(sum(item["score"] for item in last_7) / len(last_7), 1) if last_7 else None
    durations = [item.get("duration_minutes") for item in last_7 if item.get("duration_minutes") is not None]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None
    return {
        "daily": daily,
        "weekly": existing.get("weekly", []),
        "summary": {
            "latest_daily": latest,
            "latest_weekly": existing.get("summary", {}).get("latest_weekly"),
            "last_7_days_average_score": avg_score,
            "last_7_days_average_duration_minutes": avg_duration,
            "daily_row_count": len(daily),
            "weekly_row_count": len(existing.get("weekly", [])),
        },
    }


def write_report(paths: list[Path], parsed: list[dict[str, Any]], added: list[dict[str, Any]], sleep_rows: list[dict[str, Any]], dry_run: bool) -> None:
    by_type = Counter(item.get("type") for item in added)
    lines = [
        "# Garmin MCP Import Update",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Dry run: {dry_run}",
        "",
        "## Input",
        *[f"- {path}" for path in paths],
        "",
        "## Activities",
        f"- Parsed activities: {len(parsed)}",
        f"- Added activities: {len(added)}",
        f"- Added by type: {dict(by_type)}",
        "",
        "## Sleep",
        f"- Parsed sleep rows: {len(sleep_rows)}",
    ]
    if added:
        lines.extend(["", "## Added Timeline"])
        for item in added:
            lines.append(
                f"- {item.get('date')} | {item.get('type')} | {item.get('name')} | "
                f"{item.get('distance_km')} km | {item.get('elapsed_time')}"
            )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = snapshot_paths(args.input)
    if not paths:
        raise SystemExit(f"No snapshot JSON files found. Checked: {args.input or [str(DEFAULT_INPUT)]}")
    payloads = [load_json(path) for path in paths]
    activities = extract_activities(payloads)
    sleep_rows = extract_sleep(payloads)
    history_path = Path(args.history)
    existing = load_list(history_path)
    merged, added = merge_history(existing, activities, args.since)
    if not args.dry_run:
        save_json(merged, history_path)
        if sleep_rows:
            save_json(merge_sleep(Path(args.sleep_output), sleep_rows), args.sleep_output)
    write_report(paths, activities, added, sleep_rows, args.dry_run)
    print(f"Snapshots read: {len(paths)}")
    print(f"Activities parsed: {len(activities)}")
    print(f"Activities added: {len(added)}")
    print(f"Sleep rows parsed: {len(sleep_rows)}")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
