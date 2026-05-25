from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    DATA_DIR,
    extract_activity,
    infer_history_type,
    load_json,
    merge_activity_metrics,
    normalize_text,
    save_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atualiza race_history.json ou training_history.json com uma nova atividade."
    )
    parser.add_argument(
        "input_path",
        help="JSON de atividade simples ou relatorio gerado por analyze_activity.py.",
    )
    parser.add_argument(
        "--history-type",
        choices=("auto", "race", "training"),
        default="auto",
        help="Tipo de historico a atualizar.",
    )
    parser.add_argument(
        "--history-path",
        help="Caminho opcional para o arquivo de historico.",
    )
    return parser.parse_args()


def default_history_path(history_type: str) -> Path:
    return DATA_DIR / ("race_history.json" if history_type == "race" else "training_history.json")


def activity_key(activity: dict[str, Any]) -> tuple[str, str]:
    return (
        str(activity.get("date") or ""),
        normalize_text(activity.get("name")),
    )


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada nao encontrado: {input_path}")

    payload = load_json(input_path)
    activity = merge_activity_metrics(extract_activity(payload))

    if args.history_type == "auto":
        category_hint = payload.get("category") if isinstance(payload, dict) else None
        history_type = infer_history_type(activity, category_hint)
    else:
        history_type = args.history_type

    history_path = Path(args.history_path) if args.history_path else default_history_path(history_type)
    history = load_json(history_path) if history_path.exists() else []
    normalized_history = [merge_activity_metrics(extract_activity(item)) for item in history]

    current_key = activity_key(activity)
    updated = False
    for index, item in enumerate(normalized_history):
        if activity_key(item) == current_key:
            normalized_history[index] = activity
            updated = True
            break

    if not updated:
        normalized_history.append(activity)

    normalized_history.sort(key=lambda item: (item.get("date") or "", item.get("name") or ""))
    save_json(normalized_history, history_path)

    action = "atualizada" if updated else "adicionada"
    print(f"Atividade {action} em {history_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
