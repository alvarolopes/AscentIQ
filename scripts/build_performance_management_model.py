from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.load_model import (  # noqa: E402
    build_daily_loads,
    build_model,
    build_recovery_summary,
    estimate_activity_load,
)

DATA_DIR = ROOT / "data"
CONTEXT_DIR = ROOT / "analysis" / "context"

TRAINING_HISTORY_PATH = DATA_DIR / "training_history.json"
RACE_HISTORY_PATH = DATA_DIR / "race_history.json"
SAMPLE_TRAINING_HISTORY_PATH = DATA_DIR / "sample_training_history.json"
SAMPLE_RACE_HISTORY_PATH = DATA_DIR / "sample_race_history.json"
SLEEP_PATH = DATA_DIR / "garmin_sleep_reference_2026_04.json"
PROFILE_PATH = DATA_DIR / "athlete_detailed_profile.json"

OUT_JSON = DATA_DIR / "performance_management_model.json"
OUT_MD = CONTEXT_DIR / "performance_management_model.md"
OUT_SVG = CONTEXT_DIR / "performance_management_chart.svg"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_history(primary_path: Path, sample_path: Path) -> list[dict[str, Any]]:
    if primary_path.exists():
        return load_json(primary_path)
    if sample_path.exists():
        return load_json(sample_path)
    return []


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    training = load_history(TRAINING_HISTORY_PATH, SAMPLE_TRAINING_HISTORY_PATH)
    races = load_history(RACE_HISTORY_PATH, SAMPLE_RACE_HISTORY_PATH)
    sleep = load_json(SLEEP_PATH) if SLEEP_PATH.exists() else None
    result = build_model(training, races, sleep, today=date.today(), generated_at=datetime.now().astimezone())
    if result is None:
        raise SystemExit("Sem atividades validas para calcular o modelo.")

    summary = result.payload["summary"]
    save_json(result.payload, OUT_JSON)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(result.markdown, encoding="utf-8")
    OUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    OUT_SVG.write_text(result.svg, encoding="utf-8")

    if PROFILE_PATH.exists():
        profile = load_json(PROFILE_PATH)
        profile["performance_management_latest"] = summary
        save_json(profile, PROFILE_PATH)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_SVG}")


if __name__ == "__main__":
    main()
