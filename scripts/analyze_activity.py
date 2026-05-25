from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from common import (
    ANALYSIS_DIR,
    DATA_DIR,
    build_best_comparison_payload,
    extract_activity,
    infer_history_type,
    load_json,
    merge_activity_metrics,
    normalize_text,
    safe_float,
    safe_int,
    save_json,
    slugify,
    utc_timestamp,
)


FIELD_ALIASES = {
    "name": {"activity name", "nome da atividade", "atividade", "name"},
    "date": {"date", "data", "start time", "hora de inicio"},
    "type": {"activity type", "tipo de atividade", "sport", "tipo"},
    "distance_km": {"distance", "distancia", "distance km", "distancia km"},
    "elapsed_time": {"elapsed time", "tempo decorrido", "duration", "tempo total"},
    "moving_time": {"moving time", "tempo em movimento"},
    "avg_hr": {
        "average hr",
        "average heart rate",
        "frequencia cardiaca media",
        "fc media",
    },
    "max_hr": {
        "max hr",
        "maximum heart rate",
        "frequencia cardiaca maxima",
        "fc maxima",
    },
    "watch_elevation_gain_m": {
        "elevation gain",
        "total ascent",
        "ganho de elevacao",
        "subida acumulada",
    },
    "pace_avg": {"average pace", "avg pace", "ritmo medio"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analisa uma atividade e gera um relatorio textual em JSON."
    )
    parser.add_argument("input_path", help="JSON manual ou CSV exportado do Garmin.")
    parser.add_argument(
        "--category",
        choices=("race", "training"),
        help="Tipo de analise. Se omitido, tenta inferir automaticamente.",
    )
    parser.add_argument(
        "--input-type",
        choices=("auto", "json", "csv"),
        default="auto",
        help="Tipo do arquivo de entrada.",
    )
    parser.add_argument(
        "--row",
        type=int,
        default=0,
        help="Linha do CSV ou item da lista JSON a analisar.",
    )
    parser.add_argument(
        "--gpx-summary",
        help="JSON gerado por parse_gpx.py para priorizar distancia e altimetria oficiais.",
    )
    parser.add_argument(
        "--notes",
        help="Arquivo .txt ou .json com observacoes subjetivas para anexar a atividade.",
    )
    parser.add_argument(
        "--history-path",
        help="Caminho opcional para o historico a ser usado na comparacao.",
    )
    parser.add_argument(
        "--output",
        help="Caminho opcional para o relatorio final.",
    )
    return parser.parse_args()


def load_activity(path: Path, input_type: str, row_index: int) -> dict[str, Any]:
    resolved_type = input_type
    if resolved_type == "auto":
        resolved_type = "csv" if path.suffix.lower() == ".csv" else "json"

    if resolved_type == "json":
        payload = load_json(path)
        if isinstance(payload, list):
            if row_index >= len(payload):
                raise IndexError("Indice fora do intervalo da lista JSON.")
            return extract_activity(payload[row_index])
        return extract_activity(payload)

    if resolved_type == "csv":
        return load_activity_from_csv(path, row_index)

    raise ValueError(f"Tipo de entrada nao suportado: {resolved_type}")


def load_activity_from_csv(path: Path, row_index: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(2048)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(file, dialect=dialect)
        rows = list(reader)

    if row_index >= len(rows):
        raise IndexError("Indice fora do intervalo do CSV.")

    row = rows[row_index]
    activity: dict[str, Any] = {}

    for target_field, aliases in FIELD_ALIASES.items():
        for raw_key, raw_value in row.items():
            if normalize_text(raw_key) in aliases:
                activity[target_field] = raw_value
                break

    if "date" in activity:
        activity["date"] = str(activity["date"])[:10]
    if "distance_km" in activity:
        activity["distance_km"] = safe_float(activity["distance_km"])
    if "avg_hr" in activity:
        activity["avg_hr"] = safe_int(activity["avg_hr"])
    if "max_hr" in activity:
        activity["max_hr"] = safe_int(activity["max_hr"])
    if "watch_elevation_gain_m" in activity:
        activity["watch_elevation_gain_m"] = safe_float(activity["watch_elevation_gain_m"])

    return activity


def load_notes(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        payload = load_json(path)
        if isinstance(payload, dict):
            return payload
        raise ValueError("Arquivo de notas JSON precisa ser um objeto.")
    return {"subjective_notes": path.read_text(encoding="utf-8").strip()}


def load_preferences() -> dict[str, Any] | None:
    preferences_path = DATA_DIR / "athlete_preferences.json"
    if preferences_path.exists():
        payload = load_json(preferences_path)
        if isinstance(payload, dict):
            return payload
    return None


def apply_gpx_priority(activity: dict[str, Any], gpx_summary: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(activity)
    if gpx_summary.get("distance_km") is not None:
        enriched["distance_km"] = gpx_summary["distance_km"]
    if gpx_summary.get("elevation_gain_m") is not None:
        enriched["official_elevation_gain_m"] = gpx_summary["elevation_gain_m"]
    for field in ("elevation_loss_m", "elevation_min_m", "elevation_max_m"):
        if gpx_summary.get(field) is not None:
            enriched[field] = gpx_summary[field]
    enriched["terrain_source"] = "official_gpx"
    enriched["gpx_summary_file"] = gpx_summary.get("source_file")
    return enriched


def classify_activity(activity: dict[str, Any]) -> str:
    activity_type = normalize_text(activity.get("type"))
    notes = normalize_text(activity.get("subjective_notes"))
    distance = safe_float(activity.get("distance_km")) or 0.0
    duration_hours = safe_float(activity.get("duration_hours")) or 0.0
    elevation_gain = safe_float(activity.get("elevation_gain_m")) or 0.0
    vertical_per_km = safe_float(activity.get("vertical_per_km")) or 0.0
    avg_hr = safe_float(activity.get("avg_hr")) or 0.0

    if "strength" in activity_type or "forca" in activity_type or "muscul" in notes:
        return "forca"
    if duration_hours <= 1.25 and distance <= 8 and avg_hr and avg_hr < 140 and elevation_gain < 200:
        return "recuperacao"
    if elevation_gain >= 700 or vertical_per_km >= 60:
        return "subida especifica"
    if avg_hr >= 160 or "limiar" in notes or "tempo" in notes:
        return "limiar"
    if duration_hours >= 2.5 or distance >= 20:
        return "longao"
    return "base aerobica"


def effort_label(activity: dict[str, Any]) -> str:
    avg_hr = safe_float(activity.get("avg_hr")) or 0.0
    duration_hours = safe_float(activity.get("duration_hours")) or 0.0
    stopped_seconds = safe_float(activity.get("stopped_time_seconds")) or 0.0
    duration_seconds = safe_float(activity.get("duration_seconds")) or 0.0

    stopped_ratio = (stopped_seconds / duration_seconds) if duration_seconds else 0.0

    if avg_hr >= 160 or (avg_hr >= 150 and duration_hours >= 3) or stopped_ratio >= 0.18:
        return "forte"
    if avg_hr >= 145 or duration_hours >= 2:
        return "moderado"
    return "controlado"


def fatigue_label(activity: dict[str, Any]) -> str:
    avg_hr = safe_float(activity.get("avg_hr")) or 0.0
    duration_hours = safe_float(activity.get("duration_hours")) or 0.0
    elevation_gain = safe_float(activity.get("elevation_gain_m")) or 0.0

    if duration_hours >= 4 or (avg_hr >= 155 and elevation_gain >= 1000):
        return "alta"
    if duration_hours >= 2.5 or avg_hr >= 145:
        return "moderada"
    return "baixa"


def terrain_label(activity: dict[str, Any]) -> str:
    vertical_per_km = safe_float(activity.get("vertical_per_km")) or 0.0
    if vertical_per_km >= 80:
        return "perfil muito vertical e exigente"
    if vertical_per_km >= 60:
        return "perfil de subida sustentada"
    if vertical_per_km >= 35:
        return "trail ondulado com subida relevante"
    return "percurso relativamente corrivel"


def season_alignment(activity: dict[str, Any], classification: str, main_goal: str) -> tuple[str, str]:
    duration_hours = safe_float(activity.get("duration_hours")) or 0.0
    elevation_gain = safe_float(activity.get("elevation_gain_m")) or 0.0

    if classification == "subida especifica":
        return (
            "alto",
            f"Estimula diretamente subida longa e tolerancia de carga, dois pilares para {main_goal}.",
        )
    if classification == "longao" and (duration_hours >= 3 or elevation_gain >= 800):
        return (
            "alto",
            f"Reforca resistencia prolongada e capacidade de sustentar esforco em terreno montanhoso para {main_goal}.",
        )
    if classification == "base aerobica":
        return (
            "bom",
            f"Ajuda a manter a base aerobica e a eficiencia cardiovascular que sustentam a preparacao para {main_goal}.",
        )
    if classification == "limiar":
        return (
            "complementar",
            f"Melhora teto fisiologico, mas precisa ser equilibrado com sessoes mais especificas de subida para {main_goal}.",
        )
    if classification == "forca":
        return (
            "estrutural",
            f"Da suporte musculoesqueletico importante para suportar mochila, desnivel e fadiga acumulada em {main_goal}.",
        )
    return (
        "indireto",
        f"Tem papel mais regenerativo, mas ainda ajuda a manter consistencia rumo a {main_goal}.",
    )


def comparison_text(comparison: dict[str, Any] | None) -> str:
    if not comparison:
        return (
            "Ainda nao existe esforco comparavel no historico dentro do criterio "
            "de ate 25% de diferenca de distancia e ate 20% de diferenca de D+."
        )

    match = comparison["matched_activity"]
    parts = [
        f"Comparavel mais proximo: {match['name']} ({match['date']}).",
        (
            f"Criterio atendido com diferenca de {comparison['criteria']['distance_diff_pct']}% "
            f"na distancia e {comparison['criteria']['elevation_diff_pct']}% no D+."
        ),
    ]

    metric_map = {
        "avg_hr": "FC media",
        "duration": "duracao",
        "vertical_speed": "vertical speed",
        "pace": "ritmo",
    }

    snippets: list[str] = []
    for key, label in metric_map.items():
        metric = comparison["metrics"].get(key)
        if not metric or metric["delta_pct"] is None:
            continue
        snippets.append(f"{label}: {metric['trend']} de {abs(metric['delta_pct'])}%")

    if snippets:
        parts.append("Evolucao observada: " + "; ".join(snippets) + ".")

    return " ".join(parts)


def recommendation_text(
    classification: str,
    effort: str,
    fatigue: str,
    preferences: dict[str, Any] | None = None,
) -> str:
    competition_philosophy = (preferences or {}).get("competition_philosophy", {})
    completion_mode = bool(competition_philosophy.get("completion_is_primary_success_metric"))

    if fatigue == "alta":
        if completion_mode:
            return (
                "Ajuste as proximas 48 a 72 horas para recuperar sem perder o objetivo principal: "
                "corrida facil, descanso relativo e retorno progressivo ao D+ para sustentar a chance de completar bem os proximos desafios."
            )
        return (
            "Priorize 48 a 72 horas de recuperacao com corrida facil ou descanso, "
            "antes de voltar a uma sessao de subida especifica."
        )
    if classification == "subida especifica":
        return (
            "Mantenha este tipo de estimulo na semana, tentando repetir em bloco controlado "
            "com menor tempo parado para melhorar continuidade de subida e aumentar sua capacidade de completar provas de montanha."
        )
    if classification == "longao":
        return (
            "Boa sessao para manter fundo. O proximo passo e encaixar um treino vertical menor "
            "na mesma semana sem sacrificar recuperacao, para transformar endurance em prontidao real para Arequipa."
        )
    if classification == "limiar":
        return (
            "Use o ganho de intensidade como ferramenta complementar, mas proteja o dia seguinte com rodagem leve para nao roubar frescor das subidas longas e da sua capacidade de completar as provas do calendario."
        )
    if effort == "controlado":
        return "Treino bem dosado. Da para progredir volume vertical gradualmente na proxima sessao-chave sem fugir da sua filosofia de endurance."
    return "Mantenha consistencia e observe sinais de fadiga antes do proximo treino exigente, com foco em sustentar seus objetivos e nao apenas em correr mais rapido."


def default_history_path(category: str) -> Path:
    return DATA_DIR / ("race_history.json" if category == "race" else "training_history.json")


def default_output_path(activity: dict[str, Any], category: str) -> Path:
    bucket = "races" if category == "race" else "trainings"
    date_part = (activity.get("date") or "unknown-date")[:10]
    name_part = slugify(activity.get("name"))
    return ANALYSIS_DIR / bucket / f"{date_part}_{name_part}_report.json"


def build_report(
    activity: dict[str, Any],
    classification: str,
    athlete_profile: dict[str, Any],
    season_goals: dict[str, Any],
    comparison: dict[str, Any] | None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, str]:
    effort = effort_label(activity)
    fatigue = fatigue_label(activity)
    terrain = terrain_label(activity)
    alignment_level, alignment_text = season_alignment(
        activity,
        classification,
        season_goals["main_goal"],
    )

    competition_philosophy = (preferences or {}).get("competition_philosophy", {})
    pace_is_primary = bool(competition_philosophy.get("pace_is_primary_objective"))
    completion_is_primary = bool(competition_philosophy.get("completion_is_primary_success_metric"))

    summary = (
        f"{activity.get('name', 'Atividade sem nome')} em {activity.get('date', 'data nao informada')}: "
        f"{activity.get('distance_km')} km, {activity.get('elevation_gain_m')} m D+, "
        f"{activity.get('elapsed_time')} totais e {activity.get('moving_time')} em movimento. "
        f"Mountain index {activity.get('mountain_index')} e vertical speed {activity.get('vertical_speed')} m/h."
    )

    pace_clause = (
        "Neste contexto, o ritmo pode ser lido como alvo central de performance. "
        if pace_is_primary
        else "Neste contexto, o ritmo entra apenas como indicador descritivo, nao como objetivo principal. "
    )

    physiological = (
        f"Esforco classificado como {effort}. FC media de {activity.get('avg_hr')} bpm, "
        f"ritmo medio de {activity.get('pace_avg')} e eficiencia cardiaca de "
        f"{activity.get('heart_rate_efficiency')} s/km por bpm. "
        f"{pace_clause}Leitura de fadiga aguda: {fatigue}."
    )

    terrain_reading = (
        f"O terreno foi interpretado como {terrain}, com {activity.get('vertical_per_km')} m de subida por km. "
        f"Fonte de altimetria priorizada: {activity.get('terrain_source', 'relogio/manual')}."
    )

    if completion_is_primary:
        impact = (
            f"Impacto no objetivo principal ({season_goals['main_goal']}): {alignment_level}. "
            f"{alignment_text} A leitura principal aqui e o quanto esta sessao aumenta sua chance de completar bem os proximos objetivos."
        )
    else:
        impact = (
            f"Impacto no objetivo principal ({season_goals['main_goal']}): {alignment_level}. "
            f"{alignment_text}"
        )

    recommendation = recommendation_text(classification, effort, fatigue, preferences)

    sports_profile = athlete_profile.get("sports_profile", [])
    sports_text = ", ".join(str(item) for item in sports_profile)

    return {
        "summary": summary,
        "physiological_reading": physiological,
        "terrain_reading": terrain_reading,
        "history_comparison": comparison_text(comparison),
        "season_impact": impact,
        "practical_recommendation": recommendation,
        "athlete_context": (
            f"Atleta: {athlete_profile.get('name')} | perfil: {sports_text}. "
            "Objetivo atual: completar provas e expedicao com endurance, usando pace apenas como contexto descritivo."
        ),
    }


def print_report(report: dict[str, str]) -> None:
    titles = {
        "summary": "1. Resumo da atividade",
        "physiological_reading": "2. Leitura fisiologica",
        "terrain_reading": "3. Leitura do terreno",
        "history_comparison": "4. Comparacao com historico",
        "season_impact": "5. Impacto no objetivo do ano",
        "practical_recommendation": "6. Recomendacao pratica",
    }

    for key in (
        "summary",
        "physiological_reading",
        "terrain_reading",
        "history_comparison",
        "season_impact",
        "practical_recommendation",
    ):
        print(titles[key])
        print(report[key])
        print()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada nao encontrado: {input_path}")

    athlete_profile = load_json(DATA_DIR / "athlete_profile.json")
    season_goals = load_json(DATA_DIR / "season_goals.json")
    preferences = load_preferences()

    activity = load_activity(input_path, args.input_type, args.row)

    if args.notes:
        activity.update(load_notes(Path(args.notes)))

    if args.gpx_summary:
        gpx_summary = load_json(args.gpx_summary)
        activity = apply_gpx_priority(activity, gpx_summary)

    activity = merge_activity_metrics(activity)
    category = args.category or infer_history_type(activity)
    classification = classify_activity(activity)

    history_path = Path(args.history_path) if args.history_path else default_history_path(category)
    history = load_json(history_path) if history_path.exists() else []
    comparison = build_best_comparison_payload(activity, history)

    report = build_report(
        activity,
        classification,
        athlete_profile,
        season_goals,
        comparison,
        preferences,
    )

    payload = {
        "analysis_type": "activity_report",
        "generated_at_utc": utc_timestamp(),
        "category": category,
        "classification": classification,
        "activity": activity,
        "comparison": comparison,
        "report": report,
        "preferences_applied": preferences,
    }

    output_path = Path(args.output) if args.output else default_output_path(activity, category)
    save_json(payload, output_path)

    print_report(report)
    print(f"Arquivo salvo em: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
