from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANALYSIS_DIR = ROOT / "analysis" / "races"

MASTER_INDEX_PATH = DATA_DIR / "activity_master_index.json"
OFFICIAL_ROUTES_PATH = ANALYSIS_DIR / "official_route_summaries.json"
RACE_HISTORY_PATH = DATA_DIR / "race_history.json"
OUTPUT_JSON_PATH = ANALYSIS_DIR / "key_races_fit_reanalysis.json"
OUTPUT_MD_PATH = ANALYSIS_DIR / "key_races_fit_reanalysis.md"

TRAIL_KEY_RACES = [
    "WTR Arraial do cabo",
    "WTR Campos do Jordão - Ultramaratona 49km",
    "WTR Serra do mar - Ultra",
    "WTR Floresta da Tijuca",
]

ROAD_KEY_RACES = [
    "26° Meia Maratona Internacional do Rio de Janeiro",
    "RJ Half Marathon",
    "Desafio da Ponte",
    "27° Meia Maratona Internacional do Rio de Janeiro",
    "Maratona de Niterói",
    "Maratona do Rio",
]

BENCHMARK_NOTES = {
    "WTR Arraial do cabo": {
        "role": "benchmark de prova compacta e cara de trilha",
        "coach_read": "FIT mostra esforco continuo e sem paradas, mas com degradacao clara no fechamento. Hoje Arraial funciona melhor como referencia de custo mecanico e de quanto a trilha curta e densa pode cobrar de voce.",
    },
    "WTR Campos do Jordão - Ultramaratona 49km": {
        "role": "benchmark de economia em ultra trail",
        "coach_read": "Campos segue como o melhor retrato de ultra trail economica: pouca parada, FC controlada para quase 50 km e fechamento forte. E a sua melhor referencia de eficiencia em trilha longa sem excesso de agressividade.",
    },
    "WTR Serra do mar - Ultra": {
        "role": "principal benchmark de montanha longa",
        "coach_read": "Serra do Mar continua sendo o benchmark mais transferivel para Arequipa. O FIT confirma carga enorme, duracao longa e fechamento forte mesmo depois do maior desgaste do seu historico.",
    },
    "WTR Floresta da Tijuca": {
        "role": "benchmark de reserva final em trilha vertical",
        "coach_read": "WTR Rio virou sua melhor referencia de densidade vertical com energia sobrando para correr no final. O FIT confirma ataque real no fechamento, e nao apenas uma descida mais favoravel.",
    },
    "26° Meia Maratona Internacional do Rio de Janeiro": {
        "role": "baseline historica de meia maratona",
        "coach_read": "A 26 Meia segue como boa baseline historica. Ela mostra um motor ja presente em 2024, mas abaixo do que voce conseguiu produzir depois em 2025.",
    },
    "RJ Half Marathon": {
        "role": "benchmark secundario de meia ondulada",
        "coach_read": "RJ Half fica como referencia secundaria e mais controlada. O fechamento foi bom, mas a altimetria de relogio nessa prova e pouco confiavel, entao ela serve mais para leitura cardiovascular do que para D+.",
    },
    "Desafio da Ponte": {
        "role": "benchmark de forca resistente em rua",
        "coach_read": "Desafio da Ponte continua muito util como referencia de forca resistente em asfalto. O FIT confirma meia consistente, sem paradas, e com fechamento firme em percurso menos plano do que a Meia do Rio.",
    },
    "27° Meia Maratona Internacional do Rio de Janeiro": {
        "role": "principal benchmark de meia maratona",
        "coach_read": "A 27 Meia permanece como seu melhor benchmark puro de meia. O FIT confirma prova limpa, sem paradas e com fechamento controlado para forte.",
    },
    "Maratona de Niterói": {
        "role": "principal benchmark de maratona competitiva",
        "coach_read": "Niteroi segue como seu melhor retrato de maratona realmente competitiva. O FIT mostra uma prova longa, praticamente sem paradas, e com fechamento ainda funcional apesar da fadiga.",
    },
    "Maratona do Rio": {
        "role": "benchmark de fundo controlado em maratona",
        "coach_read": "Maratona do Rio continua mais util como referencia de endurance controlado do que de teto competitivo. O FIT mostra uma maratona muito limpa, com custo cardiovascular relativamente bem administrado.",
    },
}


def load_json(path: Path, encoding: str = "utf-8") -> Any:
    try:
        return json.loads(path.read_text(encoding=encoding))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def fmt_num(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def pick_activity(index: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in index:
        if item.get("name") == name:
            return item
    raise KeyError(f"Activity not found: {name}")


def official_route_maps(routes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_name: dict[str, dict[str, Any]] = {}
    by_date: dict[str, dict[str, Any]] = {}
    for route in routes:
        linked = route.get("linked_activity") or {}
        linked_name = linked.get("name")
        linked_date = linked.get("date")
        if linked_name:
            by_name[linked_name] = route
        if linked_date:
            by_date[linked_date] = route
    return by_name, by_date


def race_history_maps(items: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_name: dict[str, dict[str, Any]] = {}
    by_date: dict[str, dict[str, Any]] = {}
    for item in items:
        name = item.get("name")
        date = item.get("date")
        if name:
            by_name[name] = item
        strava_name = item.get("strava_name")
        if strava_name:
            by_name[strava_name] = item
        if date:
            by_date[date] = item
    return by_name, by_date


def build_race_payload(
    activity: dict[str, Any],
    category: str,
    route_by_name: dict[str, dict[str, Any]],
    route_by_date: dict[str, dict[str, Any]],
    race_by_name: dict[str, dict[str, Any]],
    race_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fit = activity.get("fit_summary") or {}
    finish = activity.get("finish_analysis") or {}
    route = route_by_name.get(activity["name"]) or route_by_date.get(activity["date"])
    race_meta = race_by_name.get(activity["name"]) or race_by_date.get(activity["date"])
    official_gain = None
    official_distance = None
    official_source = None
    if route:
        official_gain = route.get("elevation_gain_m_selected")
        official_distance = route.get("distance_km")
        official_source = "official_gpx"
    elif race_meta and race_meta.get("official_elevation_gain_m") is not None:
        official_gain = race_meta.get("official_elevation_gain_m")
        official_distance = race_meta.get("distance_km")
        official_source = "race_history_manual"

    fit_ascent = fit.get("total_ascent_m")
    fit_distance = fit.get("total_distance_km")
    fit_elapsed = fit.get("total_elapsed_time_s")
    fit_timer = fit.get("total_timer_time_s")
    fit_stopped = fit.get("stopped_time_s")

    course_gain_delta = None
    if official_gain is not None and fit_ascent is not None:
        course_gain_delta = round(official_gain - fit_ascent, 1)

    finish_gain_5k = finish.get("last_5k_gain_s_per_km")
    finish_gain_2k = finish.get("last_2k_gain_s_per_km")

    notes = BENCHMARK_NOTES.get(activity["name"], {})

    payload = {
        "date": activity.get("date"),
        "name": activity.get("name"),
        "category": category,
        "role": notes.get("role"),
        "coach_read": notes.get("coach_read"),
        "fit_primary": {
            "distance_km": fit_distance,
            "elapsed_time": format_duration(fit_elapsed),
            "moving_time": format_duration(fit_timer),
            "stopped_time": format_duration(fit_stopped),
            "stopped_time_seconds": None if fit_stopped is None else round(fit_stopped, 1),
            "avg_hr": fit.get("avg_hr"),
            "max_hr": fit.get("max_hr"),
            "ascent_m": fit_ascent,
            "pace_moving": fit.get("pace_moving_avg"),
            "pace_elapsed": fit.get("pace_elapsed_avg"),
            "vertical_per_km": fit.get("vertical_per_km"),
            "vertical_speed_m_per_h": fit.get("vertical_speed_elapsed_m_per_h"),
            "mountain_index": fit.get("mountain_index"),
            "heart_rate_efficiency": fit.get("heart_rate_efficiency"),
            "training_effect": fit.get("total_training_effect"),
            "anaerobic_training_effect": fit.get("total_anaerobic_training_effect"),
        },
        "course_profile": {
            "official_source": official_source,
            "official_distance_km": official_distance,
            "official_gain_m": official_gain,
            "fit_gain_m": fit_ascent,
            "official_minus_fit_gain_m": course_gain_delta,
        },
        "finish_signature": {
            "signature": finish.get("final_attack_signature"),
            "last_5k_pace": (finish.get("last_5k") or {}).get("pace_avg"),
            "last_5k_avg_hr": (finish.get("last_5k") or {}).get("avg_hr"),
            "previous_5k_pace": (finish.get("previous_5k") or {}).get("pace_avg"),
            "previous_5k_avg_hr": (finish.get("previous_5k") or {}).get("avg_hr"),
            "last_5k_gain_s_per_km": finish_gain_5k,
            "last_2k_pace": (finish.get("last_2k") or {}).get("pace_avg"),
            "previous_2k_pace": (finish.get("previous_2k") or {}).get("pace_avg"),
            "last_2k_gain_s_per_km": finish_gain_2k,
        },
    }
    return payload


def trail_hierarchy(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "benchmark": "Serra do Mar",
            "why": "maior transferencia para montanha longa; maior duracao e maior carga vertical global com fechamento forte",
        },
        {
            "benchmark": "Campos do Jordao",
            "why": "melhor retrato de economia em ultra trail; baixa parada e fechamento forte em duracao longa",
        },
        {
            "benchmark": "WTR Rio",
            "why": "melhor assinatura de reserva final em trilha vertical curta-media; ataque claro no final",
        },
        {
            "benchmark": "Arraial do Cabo",
            "why": "melhor referencia de custo de trilha compacta e de final degradado sob terreno mais caro",
        },
    ]


def road_hierarchy(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "benchmark": "27 Meia do Rio",
            "why": "melhor benchmark puro de meia maratona por tempo, FC e prova limpa no FIT",
        },
        {
            "benchmark": "Desafio da Ponte",
            "why": "melhor benchmark de forca resistente em rua e percurso menos plano",
        },
        {
            "benchmark": "Maratona de Niteroi",
            "why": "melhor benchmark de maratona competitiva real",
        },
        {
            "benchmark": "Maratona do Rio",
            "why": "melhor benchmark de endurance controlado em maratona recente",
        },
    ]


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Key Races FIT Reanalysis")
    lines.append("")
    lines.append(f"Gerado em: {report['generated_at']}")
    lines.append("")
    lines.append("## 1. Criterio desta reanalise")
    lines.append("- FIT como fonte principal para distancia, tempos, FC, tempo parado e dinamica de fechamento.")
    lines.append("- GPX oficial como fonte principal para D+ de percurso nas provas de trilha quando disponivel.")
    lines.append("- Para provas de rua, D+ do relogio foi mantido apenas como contexto, porque ha sinais de inflacao em alguns FITs.")
    lines.append("")

    lines.append("## 2. Provas de trilha reanalisadas")
    for item in report["trail_races"]:
        fit = item["fit_primary"]
        course = item["course_profile"]
        finish = item["finish_signature"]
        lines.append(f"### {item['date']} - {item['name']}")
        lines.append(f"- Papel no agente: {item['role']}")
        lines.append(f"- FIT: {fmt_num(fit['distance_km'], 3)} km, {fit['elapsed_time']} total, {fit['moving_time']} em movimento, tempo parado {fit['stopped_time']}, FC media/max {fit['avg_hr']} / {fit['max_hr']}, pace mov. {fit['pace_moving']}, assinatura final {finish['signature']}.")
        if course.get("official_gain_m") is not None:
            lines.append(f"- Percurso oficial: {fmt_num(course['official_distance_km'], 3)} km, {fmt_num(course['official_gain_m'], 1)} m D+ ({course['official_source']}). FIT marcou {fmt_num(course['fit_gain_m'], 1)} m; delta oficial - FIT = {fmt_num(course['official_minus_fit_gain_m'], 1)} m.")
        else:
            lines.append(f"- Terreno: sem GPX oficial salvo; FIT marcou {fmt_num(course['fit_gain_m'], 1)} m D+.")
        lines.append(f"- Fechamento: ultimos 5 km em {finish['last_5k_pace']} contra {finish['previous_5k_pace']} no bloco anterior; ganho de {fmt_num(finish['last_5k_gain_s_per_km'], 1)} s/km. Ultimos 2 km em {finish['last_2k_pace']} contra {finish['previous_2k_pace']}.")
        lines.append(f"- Leitura de treinador: {item['coach_read']}")
        lines.append("")

    lines.append("## 3. Provas de rua reanalisadas")
    for item in report["road_races"]:
        fit = item["fit_primary"]
        finish = item["finish_signature"]
        lines.append(f"### {item['date']} - {item['name']}")
        lines.append(f"- Papel no agente: {item['role']}")
        lines.append(f"- FIT: {fmt_num(fit['distance_km'], 3)} km, {fit['elapsed_time']} total, tempo parado {fit['stopped_time']}, FC media/max {fit['avg_hr']} / {fit['max_hr']}, pace mov. {fit['pace_moving']}, assinatura final {finish['signature']}.")
        lines.append(f"- Fechamento: ultimos 5 km em {finish['last_5k_pace']} contra {finish['previous_5k_pace']} no bloco anterior; ganho de {fmt_num(finish['last_5k_gain_s_per_km'], 1)} s/km. Ultimos 2 km em {finish['last_2k_pace']} contra {finish['previous_2k_pace']}.")
        lines.append(f"- Leitura de treinador: {item['coach_read']}")
        lines.append("")

    lines.append("## 4. Hierarquia atual dos benchmarks")
    lines.append("### Trilha")
    for item in report["benchmark_hierarchy"]["trail"]:
        lines.append(f"- {item['benchmark']}: {item['why']}")
    lines.append("")
    lines.append("### Rua")
    for item in report["benchmark_hierarchy"]["road"]:
        lines.append(f"- {item['benchmark']}: {item['why']}")
    lines.append("")

    lines.append("## 5. O que mudou com a base FIT")
    for item in report["fit_first_takeaways"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 6. Impacto no objetivo Arequipa")
    for item in report["season_transfer"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 7. Resumo executivo")
    lines.append(f"- Melhor benchmark atual de montanha longa: {report['executive_summary']['best_long_mountain_benchmark']}")
    lines.append(f"- Melhor benchmark atual de economia em ultra trail: {report['executive_summary']['best_ultra_economy_benchmark']}")
    lines.append(f"- Melhor benchmark atual de reserva final em trilha: {report['executive_summary']['best_late_reserve_trail_benchmark']}")
    lines.append(f"- Principal benchmark de meia maratona: {report['executive_summary']['best_half_marathon_benchmark']}")
    lines.append(f"- Principal benchmark de maratona competitiva: {report['executive_summary']['best_marathon_benchmark']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    master_index = load_json(MASTER_INDEX_PATH)
    official_routes = load_json(OFFICIAL_ROUTES_PATH)
    race_history = load_json(RACE_HISTORY_PATH, encoding="utf-8-sig")
    route_by_name, route_by_date = official_route_maps(official_routes)
    race_by_name, race_by_date = race_history_maps(race_history)

    trail_payload = [
        build_race_payload(pick_activity(master_index, name), "trail", route_by_name, route_by_date, race_by_name, race_by_date)
        for name in TRAIL_KEY_RACES
    ]
    road_payload = [
        build_race_payload(pick_activity(master_index, name), "road", route_by_name, route_by_date, race_by_name, race_by_date)
        for name in ROAD_KEY_RACES
    ]

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "methodology": {
            "fit_primary_for": [
                "distance",
                "elapsed_time",
                "moving_time",
                "stopped_time",
                "average_heart_rate",
                "finish_dynamics",
            ],
            "official_route_primary_for": [
                "trail_race_course_distance",
                "trail_race_course_elevation_gain",
            ],
            "road_d_plus_note": "Road-race ascent from FIT is kept as secondary context because some files show implausibly inflated watch altitude gain.",
        },
        "trail_races": trail_payload,
        "road_races": road_payload,
        "benchmark_hierarchy": {
            "trail": trail_hierarchy(trail_payload),
            "road": road_hierarchy(road_payload),
        },
        "fit_first_takeaways": [
            "WTR Rio sobe de status: o FIT confirmou um fechamento realmente forte, com melhora grande no ultimo bloco sem alta proporcional de FC.",
            "Campos do Jordao fica ainda mais solido como benchmark de economia em ultra trail porque o FIT confirma pouca parada e fechamento forte.",
            "Serra do Mar se consolida como principal benchmark de montanha longa: grande carga, grande duracao e assinatura final forte.",
            "Arraial passa a ser lido com mais clareza como prova compacta e cara, de fechamento degradado, e nao como prova com reserva final preservada.",
            "Nas provas de rua, o FIT melhorou muito a leitura de fechamento e confiou pouco em D+; por isso meia e maratona devem ser comparadas mais por tempo, FC e assinatura final do que por altimetria de relogio.",
        ],
        "season_transfer": [
            "Seu bloco de provas mostra que o motor de endurance esta estabelecido tanto em rua quanto em trilha.",
            "Para Arequipa, as provas mais transferiveis hoje sao Serra do Mar como benchmark de montanha longa, Campos como benchmark de economia e WTR Rio como benchmark de reserva final em subida.",
            "O gargalo continua sendo continuidade de especificidade vertical, nao falta de capacidade para competir ou completar provas longas.",
            "As provas de rua seguem uteis como manutencao competitiva e de base aerobica, mas nao substituem hike tecnico e corrida com D+ regular.",
        ],
        "executive_summary": {
            "best_long_mountain_benchmark": "WTR Serra do Mar - Ultra",
            "best_ultra_economy_benchmark": "WTR Campos do Jordao - Ultramaratona 49km",
            "best_late_reserve_trail_benchmark": "WTR Floresta da Tijuca",
            "best_half_marathon_benchmark": "27 Meia Maratona Internacional do Rio de Janeiro",
            "best_marathon_benchmark": "Maratona de Niteroi",
        },
    }

    OUTPUT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD_PATH.write_text(build_markdown(report), encoding="utf-8")
    print(f"Wrote {OUTPUT_JSON_PATH}")
    print(f"Wrote {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
