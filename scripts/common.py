from __future__ import annotations

import json
import math
import unicodedata
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"


def utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def slugify(value: Any) -> str:
    normalized = normalize_text(value)
    chars: list[str] = []
    for char in normalized:
        if char.isalnum():
            chars.append(char)
        elif char in {" ", "-", "_", "/"}:
            chars.append("-")
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "activity"


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = (
        text.replace("km", "")
        .replace("m", "")
        .replace("%", "")
        .replace("bpm", "")
        .strip()
    )

    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    elif text.count(",") >= 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


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
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(round(float(parts[2])))
        return hours * 3600 + minutes * 60 + seconds

    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = int(round(float(parts[1])))
        return minutes * 60 + seconds

    return None


def pace_to_seconds_per_km(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    for token in ("/km", "min/km", " pace"):
        text = text.replace(token, "")

    parsed = parse_duration_to_seconds(text)
    return float(parsed) if parsed is not None else None


def format_duration(seconds: int | float | None) -> str | None:
    if seconds is None:
        return None
    total_seconds = int(round(float(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    total_seconds = int(round(seconds_per_km))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}/km"


def round_or_none(value: float | None, decimals: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, decimals)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data: Any, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return output_path


def extract_activity(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("activity", "reference_activity"):
            activity = payload.get(key)
            if isinstance(activity, dict):
                return activity
        return payload
    raise ValueError("Atividade inválida: esperado um objeto JSON.")


def preferred_elevation_gain(activity: dict[str, Any]) -> float | None:
    for key in ("official_elevation_gain_m", "elevation_gain_m", "watch_elevation_gain_m"):
        value = safe_float(activity.get(key))
        if value is not None:
            return value
    return None


def compute_metrics(activity: dict[str, Any]) -> dict[str, Any]:
    distance_km = safe_float(activity.get("distance_km"))
    elevation_gain_m = preferred_elevation_gain(activity)
    elapsed_seconds = parse_duration_to_seconds(
        activity.get("elapsed_time")
        or activity.get("duration")
        or activity.get("duration_seconds")
    )
    moving_seconds = parse_duration_to_seconds(
        activity.get("moving_time") or activity.get("moving_time_seconds")
    )
    avg_hr = safe_float(activity.get("avg_hr"))

    if moving_seconds is None and elapsed_seconds is not None:
        moving_seconds = elapsed_seconds
    if (
        elapsed_seconds is not None
        and moving_seconds is not None
        and moving_seconds > elapsed_seconds
    ):
        moving_seconds = elapsed_seconds

    stopped_seconds = (
        elapsed_seconds - moving_seconds
        if elapsed_seconds is not None and moving_seconds is not None
        else None
    )

    pace_seconds_per_km = pace_to_seconds_per_km(activity.get("pace_avg"))
    if pace_seconds_per_km is None and elapsed_seconds and distance_km:
        pace_seconds_per_km = elapsed_seconds / distance_km

    duration_hours = elapsed_seconds / 3600 if elapsed_seconds else None
    moving_hours = moving_seconds / 3600 if moving_seconds else None

    vertical_per_km = (
        elevation_gain_m / distance_km
        if elevation_gain_m is not None and distance_km
        else None
    )
    vertical_speed = (
        elevation_gain_m / duration_hours
        if elevation_gain_m is not None and duration_hours
        else None
    )
    vertical_speed_moving = (
        elevation_gain_m / moving_hours
        if elevation_gain_m is not None and moving_hours
        else None
    )
    mountain_index = (
        distance_km + elevation_gain_m / 100
        if distance_km is not None and elevation_gain_m is not None
        else None
    )
    heart_rate_efficiency = (
        pace_seconds_per_km / avg_hr
        if pace_seconds_per_km is not None and avg_hr
        else None
    )

    return {
        "distance_km": round_or_none(distance_km, 2),
        "elevation_gain_m": round_or_none(elevation_gain_m, 1),
        "duration_seconds": elapsed_seconds,
        "duration_hours": round_or_none(duration_hours, 3),
        "moving_time_seconds": moving_seconds,
        "moving_time_hours": round_or_none(moving_hours, 3),
        "stopped_time_seconds": stopped_seconds,
        "pace_seconds_per_km": round_or_none(pace_seconds_per_km, 2),
        "vertical_per_km": round_or_none(vertical_per_km, 2),
        "vertical_speed": round_or_none(vertical_speed, 1),
        "vertical_speed_moving": round_or_none(vertical_speed_moving, 1),
        "mountain_index": round_or_none(mountain_index, 2),
        "heart_rate_efficiency": round_or_none(heart_rate_efficiency, 3),
        "avg_hr": round_or_none(avg_hr, 1),
    }


def merge_activity_metrics(activity: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(activity)
    metrics = compute_metrics(normalized)
    normalized.update(metrics)

    if metrics.get("duration_seconds") is not None:
        normalized["elapsed_time"] = normalized.get("elapsed_time") or format_duration(
            metrics["duration_seconds"]
        )
    if metrics.get("moving_time_seconds") is not None:
        normalized["moving_time"] = normalized.get("moving_time") or format_duration(
            metrics["moving_time_seconds"]
        )
    if metrics.get("stopped_time_seconds") is not None:
        normalized["stopped_time"] = format_duration(metrics["stopped_time_seconds"])
    if metrics.get("pace_seconds_per_km") is not None:
        normalized["pace_avg"] = normalized.get("pace_avg") or format_pace(
            metrics["pace_seconds_per_km"]
        )
    if metrics.get("avg_hr") is not None and math.isclose(
        metrics["avg_hr"], round(metrics["avg_hr"])
    ):
        normalized["avg_hr"] = int(round(metrics["avg_hr"]))
    if metrics.get("elevation_gain_m") is not None:
        normalized["elevation_gain_m"] = metrics["elevation_gain_m"]

    return normalized


def percent_difference(reference: float | None, candidate: float | None) -> float | None:
    if reference is None or candidate is None:
        return None
    if reference == 0:
        return 0.0 if candidate == 0 else None
    return abs(candidate - reference) / abs(reference)


def find_comparable_activities(
    reference: dict[str, Any],
    history: list[dict[str, Any]],
    max_distance_diff: float = 0.25,
    max_elevation_diff: float = 0.20,
) -> list[dict[str, Any]]:
    normalized_reference = merge_activity_metrics(extract_activity(reference))
    reference_name = normalize_text(normalized_reference.get("name"))
    reference_date = normalized_reference.get("date")

    matches: list[dict[str, Any]] = []

    for item in history:
        normalized_item = merge_activity_metrics(extract_activity(item))

        if (
            normalize_text(normalized_item.get("name")) == reference_name
            and normalized_item.get("date") == reference_date
        ):
            continue

        distance_diff = percent_difference(
            safe_float(normalized_reference.get("distance_km")),
            safe_float(normalized_item.get("distance_km")),
        )
        elevation_diff = percent_difference(
            safe_float(normalized_reference.get("elevation_gain_m")),
            safe_float(normalized_item.get("elevation_gain_m")),
        )

        if distance_diff is None or elevation_diff is None:
            continue
        if distance_diff > max_distance_diff or elevation_diff > max_elevation_diff:
            continue

        score = distance_diff + elevation_diff
        matches.append(
            {
                "activity": normalized_item,
                "distance_diff_pct": round(distance_diff * 100, 2),
                "elevation_diff_pct": round(elevation_diff * 100, 2),
                "score": round(score, 4),
            }
        )

    return sorted(
        matches,
        key=lambda item: (
            item["score"],
            item["activity"].get("date") or "",
            item["activity"].get("name") or "",
        ),
    )


def metric_delta(
    current: float | None,
    previous: float | None,
    *,
    lower_is_better: bool,
    decimals: int = 2,
) -> dict[str, Any] | None:
    if current is None or previous is None:
        return None

    delta = current - previous
    delta_pct = None if previous == 0 else (delta / previous) * 100
    tolerance = 0.01 if decimals >= 2 else 0.1

    if abs(delta) <= tolerance:
        trend = "estável"
    else:
        improved = delta < 0 if lower_is_better else delta > 0
        trend = "melhora" if improved else "piora"

    return {
        "current": round(current, decimals),
        "previous": round(previous, decimals),
        "delta": round(delta, decimals),
        "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
        "trend": trend,
    }


def build_best_comparison_payload(
    reference: dict[str, Any], history: list[dict[str, Any]]
) -> dict[str, Any] | None:
    matches = find_comparable_activities(reference, history)
    if not matches:
        return None

    normalized_reference = merge_activity_metrics(extract_activity(reference))
    best_match = matches[0]
    candidate = best_match["activity"]

    return {
        "matched_activity": {
            "name": candidate.get("name"),
            "date": candidate.get("date"),
            "type": candidate.get("type"),
        },
        "criteria": {
            "distance_diff_pct": best_match["distance_diff_pct"],
            "elevation_diff_pct": best_match["elevation_diff_pct"],
        },
        "metrics": {
            "avg_hr": metric_delta(
                safe_float(normalized_reference.get("avg_hr")),
                safe_float(candidate.get("avg_hr")),
                lower_is_better=True,
                decimals=1,
            ),
            "duration": metric_delta(
                safe_float(normalized_reference.get("duration_seconds")),
                safe_float(candidate.get("duration_seconds")),
                lower_is_better=True,
                decimals=0,
            ),
            "vertical_speed": metric_delta(
                safe_float(normalized_reference.get("vertical_speed")),
                safe_float(candidate.get("vertical_speed")),
                lower_is_better=False,
                decimals=1,
            ),
            "pace": metric_delta(
                safe_float(normalized_reference.get("pace_seconds_per_km")),
                safe_float(candidate.get("pace_seconds_per_km")),
                lower_is_better=True,
                decimals=1,
            ),
        },
        "comparable_count": len(matches),
    }


def infer_history_type(activity: dict[str, Any], category_hint: str | None = None) -> str:
    if category_hint in {"race", "training"}:
        return category_hint

    activity_type = normalize_text(activity.get("type"))
    if "race" in activity_type or "prova" in activity_type:
        return "race"
    return "training"
