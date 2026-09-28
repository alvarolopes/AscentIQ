from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sync_start(history: list[dict], end: date, fallback: date, overlap_days: int) -> date:
    if overlap_days < 0:
        raise ValueError("overlap_days must be non-negative")
    garmin_dates: list[date] = []
    for item in history:
        source = str(item.get("source") or "")
        if not item.get("garmin_activity_id") and "garmin" not in source.lower():
            continue
        try:
            activity_date = date.fromisoformat(str(item.get("date") or "")[:10])
        except ValueError:
            continue
        if activity_date <= end:
            garmin_dates.append(activity_date)
    if not garmin_dates:
        return min(fallback, end)
    return max(fallback, max(garmin_dates) - timedelta(days=overlap_days))


def main() -> int:
    parser = argparse.ArgumentParser(description="Find the next Garmin activity sync window.")
    parser.add_argument("--history", default=str(ROOT / "data" / "training_history.json"))
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--fallback-date", default="2024-01-01")
    parser.add_argument("--overlap-days", type=int, default=7)
    args = parser.parse_args()
    history_path = Path(args.history)
    history = json.loads(history_path.read_text(encoding="utf-8-sig")) if history_path.exists() else []
    if not isinstance(history, list):
        raise ValueError("Training history must be a JSON list")
    print(sync_start(history, date.fromisoformat(args.end_date), date.fromisoformat(args.fallback_date), args.overlap_days).isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
