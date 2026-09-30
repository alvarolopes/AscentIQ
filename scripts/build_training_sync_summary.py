from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_PATH = ROOT / "analysis" / "context" / "training_sync_latest.md"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    history = load_json(DATA_DIR / "training_history.json", [])
    hevy = load_json(DATA_DIR / "hevy_workouts.json", [])
    consolidated = load_json(DATA_DIR / "strength_training_consolidated.json", [])
    pmc = load_json(DATA_DIR / "performance_management_model.json", {})
    dashboard = load_json(DATA_DIR / "current_performance_dashboard.json", {})

    matched = sum(1 for row in consolidated if row.get("garmin_match_status") == "matched")
    unmatched = sum(1 for row in consolidated if row.get("garmin_match_status") == "unmatched_hevy")
    garmin_only = sum(1 for row in consolidated if row.get("garmin_match_status") == "garmin_only")
    class_counts = Counter(str(item.get("classification") or "strength") for item in hevy)
    total_volume = sum(float(item.get("total_volume_kg") or 0) for item in hevy)
    latest_activities = sorted(
        (item for item in history if item.get("date")),
        key=lambda item: (str(item.get("date")), str(item.get("date_time") or "")),
    )[-8:]
    summary = pmc.get("summary") or {}
    goal = dashboard.get("goal_context") or {}
    goal_snapshot = dashboard.get("current_goal_snapshot") or dashboard.get("arequipa_snapshot") or {}

    lines = [
        "# Latest unified training sync",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## Imported database",
        "",
        f"- Total local activities: {len(history)}",
        f"- Hevy workouts: {len(hevy)}",
        f"- Hevy matched with Garmin strength: {matched}",
        f"- Hevy without Garmin match: {unmatched}",
        f"- Garmin strength without Hevy match: {garmin_only}",
        f"- Hevy total recorded volume: {total_volume:,.1f} kg",
        f"- Hevy classifications: {dict(sorted(class_counts.items()))}",
        "",
        "## Current model",
        "",
        f"- Model date: {summary.get('latest_date')}",
        f"- Fitness: {summary.get('fitness')}",
        f"- Fatigue: {summary.get('fatigue')}",
        f"- Form: {summary.get('form')}",
        f"- Recovery: {(summary.get('recovery') or {}).get('score')} ({(summary.get('recovery') or {}).get('status')})",
        f"- Current goal: {goal.get('label') or goal.get('main_goal')}",
        f"- Goal readiness score: {goal_snapshot.get('score')} ({goal_snapshot.get('band')})",
        "",
        "## Latest activities",
        "",
        "| Date | Type | Name | Duration | Distance | Hevy detail |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in latest_activities:
        lines.append(
            f"| {item.get('date')} | {item.get('type')} | {item.get('name')} | "
            f"{item.get('elapsed_time') or item.get('moving_time') or ''} | "
            f"{item.get('distance_km') or ''} | {item.get('hevy_title') or ''} |"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
