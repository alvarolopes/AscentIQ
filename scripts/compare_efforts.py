from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    ANALYSIS_DIR,
    DATA_DIR,
    build_best_comparison_payload,
    extract_activity,
    find_comparable_activities,
    infer_history_type,
    load_json,
    merge_activity_metrics,
    save_json,
    slugify,
    utc_timestamp,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara uma atividade com o historico usando similaridade de distancia e D+."
    )
    parser.add_argument(
        "reference_path",
        help="JSON de atividade simples ou relatorio gerado por analyze_activity.py.",
    )
    parser.add_argument(
        "--category",
        choices=("race", "training"),
        help="Tipo de historico a consultar.",
    )
    parser.add_argument(
        "--history-path",
        help="Caminho opcional para o historico JSON.",
    )
    parser.add_argument(
        "--output",
        help="Caminho opcional para salvar o comparativo.",
    )
    return parser.parse_args()


def default_history_path(category: str) -> Path:
    return DATA_DIR / ("race_history.json" if category == "race" else "training_history.json")


def default_output_path(activity: dict[str, Any], category: str) -> Path:
    bucket = "races" if category == "race" else "trainings"
    date_part = (activity.get("date") or "unknown-date")[:10]
    name_part = slugify(activity.get("name"))
    return ANALYSIS_DIR / bucket / f"{date_part}_{name_part}_comparison.json"


def serialize_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for match in matches:
        activity = match["activity"]
        serialized.append(
            {
                "name": activity.get("name"),
                "date": activity.get("date"),
                "type": activity.get("type"),
                "distance_km": activity.get("distance_km"),
                "elevation_gain_m": activity.get("elevation_gain_m"),
                "duration": activity.get("elapsed_time"),
                "avg_hr": activity.get("avg_hr"),
                "pace_avg": activity.get("pace_avg"),
                "vertical_speed": activity.get("vertical_speed"),
                "distance_diff_pct": match["distance_diff_pct"],
                "elevation_diff_pct": match["elevation_diff_pct"],
                "score": match["score"],
            }
        )
    return serialized


def print_summary(reference: dict[str, Any], comparison: dict[str, Any] | None) -> None:
    print(
        f"Referencia: {reference.get('name')} ({reference.get('date')}) | "
        f"{reference.get('distance_km')} km | {reference.get('elevation_gain_m')} m D+"
    )

    if not comparison:
        print("Nenhum esforco comparavel encontrado dentro dos criterios.")
        return

    match = comparison["matched_activity"]
    print(f"Melhor comparavel: {match['name']} ({match['date']})")
    print(
        f"Diferenca: {comparison['criteria']['distance_diff_pct']}% na distancia | "
        f"{comparison['criteria']['elevation_diff_pct']}% no D+"
    )

    for label, key in (
        ("FC media", "avg_hr"),
        ("Duracao", "duration"),
        ("Vertical speed", "vertical_speed"),
        ("Ritmo", "pace"),
    ):
        metric = comparison["metrics"].get(key)
        if metric:
            print(f"{label}: {metric['trend']} ({metric['delta_pct']}%)")


def main() -> int:
    args = parse_args()
    reference_path = Path(args.reference_path)
    if not reference_path.exists():
        raise FileNotFoundError(f"Arquivo de referencia nao encontrado: {reference_path}")

    reference_payload = load_json(reference_path)
    reference_activity = merge_activity_metrics(extract_activity(reference_payload))
    category = args.category or infer_history_type(reference_activity)

    history_path = Path(args.history_path) if args.history_path else default_history_path(category)
    history = load_json(history_path) if history_path.exists() else []

    matches = find_comparable_activities(reference_activity, history)
    comparison = build_best_comparison_payload(reference_activity, history)

    payload = {
        "analysis_type": "effort_comparison",
        "generated_at_utc": utc_timestamp(),
        "category": category,
        "reference_activity": reference_activity,
        "criteria": {
            "max_distance_diff_pct": 25,
            "max_elevation_diff_pct": 20,
        },
        "best_match": comparison,
        "comparables": serialize_matches(matches),
    }

    output_path = Path(args.output) if args.output else default_output_path(reference_activity, category)
    save_json(payload, output_path)

    print_summary(reference_activity, comparison)
    print(f"Comparativo salvo em: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
