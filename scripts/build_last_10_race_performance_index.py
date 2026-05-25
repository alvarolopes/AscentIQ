from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANALYSIS_DIR = ROOT / "analysis" / "races"
MASTER_INDEX_PATH = DATA_DIR / "activity_master_index.json"
RACE_HISTORY_PATH = DATA_DIR / "race_history.json"
OUTPUT_JSON_PATH = ANALYSIS_DIR / "last_10_race_performance_index.json"
OUTPUT_MD_PATH = ANALYSIS_DIR / "last_10_race_performance_index.md"
OUTPUT_SVG_PATH = ANALYSIS_DIR / "last_10_race_performance_chart.svg"

LOW_CONFIDENCE_NAMES = {"2 Corrida da Portela"}
COLOR_TRAIL = "#2f7d32"
COLOR_ROAD = "#1f5aa6"
COLOR_LOW = "#7a7a7a"
COLOR_CURRENT = "#d9480f"
BG = "#f7f4ed"
GRID = "#d6d0c3"
TEXT = "#1f1c17"
SUBTEXT = "#5b5449"

SHORT_LABELS = {
    "RJ Half Marathon": "RJ Half",
    "WTR Arraial do cabo": "Arraial",
    "10km na Maratona do  Rio": "10k Rio",
    "Maratona do Rio": "Maratona Rio",
    "Desafio da Ponte": "Ponte",
    "27° Meia Maratona Internacional do Rio de Janeiro": "27 Meia",
    "WTR Campos do Jordão - Ultramaratona 49km": "Campos",
    "WTR Serra do mar - Ultra": "Serra",
    "2 Corrida da Portela": "Portela",
    "WTR Floresta da Tijuca": "WTR Rio",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def cluster_for_race(race: dict[str, Any]) -> str:
    fit = race.get("fit_summary") or {}
    distance = fit.get("total_distance_km") or race.get("distance_km") or 0
    subtype = (race.get("subtype") or "").lower()
    if "trail" in subtype:
        return "trail_ultra" if distance >= 30 else "trail_mid"
    if distance >= 30:
        return "road_long"
    if distance >= 15:
        return "road_half"
    return "road_short"


def norm(values: list[float | None], value: float | None, *, lower_better: bool = False) -> float:
    clean = [x for x in values if x is not None]
    if value is None or not clean:
        return 0.5
    lo = min(clean)
    hi = max(clean)
    if hi == lo:
        return 0.5
    score = (value - lo) / (hi - lo)
    if lower_better:
        score = 1 - score
    return max(0.0, min(1.0, score))


def format_hours(seconds: float | None) -> float | None:
    if seconds is None:
        return None
    return round(seconds / 3600.0, 2)


def format_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100.0, 1)


def official_gain_for_race(race: dict[str, Any], race_meta_by_name: dict[str, Any]) -> float:
    race_meta = race_meta_by_name.get(race.get("name"))
    if race_meta and race_meta.get("official_elevation_gain_m") is not None:
        return float(race_meta["official_elevation_gain_m"])
    subtype = (race.get("subtype") or "").lower()
    if "trail" in subtype:
        fit_gain = (race.get("fit_summary") or {}).get("total_ascent_m")
        if fit_gain is not None:
            return float(fit_gain)
    return 0.0


def confidence_for_race(race: dict[str, Any]) -> str:
    return "low" if race.get("name") in LOW_CONFIDENCE_NAMES else "high"


def band_for_score(score: float) -> str:
    if score >= 75:
        return "muito forte"
    if score >= 60:
        return "forte"
    if score >= 45:
        return "solida"
    return "comprometida"


def short_label(name: str) -> str:
    return SHORT_LABELS.get(name, name)


def build_svg(entries: list[dict[str, Any]]) -> str:
    width = 1400
    height = 880
    margin_left = 90
    margin_right = 40
    top_chart_top = 90
    top_chart_height = 250
    bottom_chart_top = 450
    bottom_chart_height = 250
    baseline_width = width - margin_left - margin_right
    bar_gap = 18
    count = len(entries)
    bar_width = (baseline_width - bar_gap * (count - 1)) / count
    max_hours = max(entry["elapsed_hours"] for entry in entries if entry["elapsed_hours"] is not None)
    title = "Ultimas 10 provas: tempo e IEP-100"

    def x_for(index: int) -> float:
        return margin_left + index * (bar_width + bar_gap)

    def top_y(value: float) -> float:
        usable = top_chart_height - 10
        return top_chart_top + top_chart_height - (value / max_hours) * usable

    def bottom_y(value: float) -> float:
        usable = bottom_chart_height - 10
        return bottom_chart_top + bottom_chart_height - (value / 100.0) * usable

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="{margin_left}" y="45" font-size="32" font-family="Georgia, serif" fill="{TEXT}" font-weight="700">{title}</text>',
        f'<text x="{margin_left}" y="72" font-size="16" font-family="Verdana, sans-serif" fill="{SUBTEXT}">IEP-100 = indice de execucao de prova, focado em fechamento, continuidade, economia equivalente e velocidade equivalente.</text>',
    ]

    for step in range(0, int(max_hours) + 2, 2):
        y = top_y(step)
        parts.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 5:.1f}" text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{step}h</text>')

    for step in range(0, 101, 20):
        y = bottom_y(step)
        parts.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 5:.1f}" text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{step}</text>')

    parts.append(f'<text x="{margin_left}" y="{top_chart_top - 20}" font-size="20" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">Tempo total FIT (horas)</text>')
    parts.append(f'<text x="{margin_left}" y="{bottom_chart_top - 20}" font-size="20" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">IEP-100</text>')

    for idx, entry in enumerate(entries):
        x = x_for(idx)
        color = COLOR_LOW if entry["confidence"] == "low" else (COLOR_TRAIL if entry["category"] == "trail" else COLOR_ROAD)
        stroke = COLOR_CURRENT if entry["is_current"] else "none"
        stroke_width = 4 if entry["is_current"] else 0

        top = top_y(entry["elapsed_hours"])
        top_height = top_chart_top + top_chart_height - top
        bottom = bottom_y(entry["performance_execution_index"])
        bottom_height = bottom_chart_top + bottom_chart_height - bottom

        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_width:.1f}" height="{top_height:.1f}" rx="6" fill="{color}" opacity="0.85" stroke="{stroke}" stroke-width="{stroke_width}"/>')
        parts.append(f'<rect x="{x:.1f}" y="{bottom:.1f}" width="{bar_width:.1f}" height="{bottom_height:.1f}" rx="6" fill="{color}" opacity="0.85" stroke="{stroke}" stroke-width="{stroke_width}"/>')

        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{top - 8:.1f}" text-anchor="middle" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{entry["elapsed_hours"]:.2f}h</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{bottom - 8:.1f}" text-anchor="middle" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{entry["performance_execution_index"]:.1f}</text>')

        label_x = x + bar_width / 2
        label_y = bottom_chart_top + bottom_chart_height + 78
        date_label = entry["date"][5:]
        race_label = short_label(entry["name"])
        parts.append(f'<g transform="translate({label_x:.1f},{label_y:.1f}) rotate(-32)">')
        parts.append(f'<text text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{date_label} | {race_label}</text>')
        parts.append('</g>')

    legend_y = 785
    parts.append(f'<rect x="{margin_left}" y="{legend_y}" width="18" height="18" fill="{COLOR_TRAIL}" opacity="0.85"/>')
    parts.append(f'<text x="{margin_left + 28}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">Trilha</text>')
    parts.append(f'<rect x="{margin_left + 120}" y="{legend_y}" width="18" height="18" fill="{COLOR_ROAD}" opacity="0.85"/>')
    parts.append(f'<text x="{margin_left + 148}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">Rua</text>')
    parts.append(f'<rect x="{margin_left + 220}" y="{legend_y}" width="18" height="18" fill="{COLOR_LOW}" opacity="0.85"/>')
    parts.append(f'<text x="{margin_left + 248}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">Baixa confianca</text>')
    parts.append(f'<rect x="{margin_left + 390}" y="{legend_y}" width="18" height="18" fill="white" stroke="{COLOR_CURRENT}" stroke-width="3"/>')
    parts.append(f'<text x="{margin_left + 418}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">Prova mais recente</text>')
    parts.append(f'<text x="{margin_left}" y="{legend_y + 42}" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">Cronologia da esquerda para a direita.</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main() -> None:
    master = load_json(MASTER_INDEX_PATH)
    race_history = load_json(RACE_HISTORY_PATH)
    race_meta_by_name: dict[str, dict[str, Any]] = {}
    for row in race_history:
        if row.get("name"):
            race_meta_by_name[row["name"]] = row
        if row.get("strava_name"):
            race_meta_by_name[row["strava_name"]] = row

    races = [row for row in master if row.get("is_race_candidate") and row.get("fit_status") == "parsed"]
    races.sort(key=lambda row: (row.get("date", ""), row.get("date_time", "")))

    for race in races:
        fit = race.get("fit_summary") or {}
        elapsed_s = fit.get("total_elapsed_time_s") or race.get("elapsed_time_seconds")
        distance_km = fit.get("total_distance_km") or race.get("distance_km") or 0.0
        official_gain = official_gain_for_race(race, race_meta_by_name)
        equivalent_distance_km = distance_km + (official_gain / 100.0 if "trail" in (race.get("subtype") or "").lower() else 0.0)
        equivalent_pace = (elapsed_s / equivalent_distance_km) if equivalent_distance_km else None
        avg_hr = fit.get("avg_hr")
        equivalent_hr_efficiency = (equivalent_pace / avg_hr) if avg_hr else None
        stopped_ratio = ((fit.get("stopped_time_s") or 0.0) / elapsed_s) if elapsed_s else 0.0

        race["cluster"] = cluster_for_race(race)
        race["confidence"] = confidence_for_race(race)
        race["official_gain_m_for_index"] = official_gain
        race["equivalent_distance_km"] = equivalent_distance_km
        race["equivalent_pace_s_per_km"] = equivalent_pace
        race["equivalent_hr_efficiency"] = equivalent_hr_efficiency
        race["stopped_ratio"] = stopped_ratio

    cluster_baselines: dict[str, list[dict[str, Any]]] = {}
    for race in races:
        if race["confidence"] != "low":
            cluster_baselines.setdefault(race["cluster"], []).append(race)

    for cluster, items in cluster_baselines.items():
        eq_pace_values = [item.get("equivalent_pace_s_per_km") for item in items]
        eq_hre_values = [item.get("equivalent_hr_efficiency") for item in items]
        stop_values = [item.get("stopped_ratio") for item in items]
        gain_values = [(item.get("finish_analysis") or {}).get("last_5k_gain_s_per_km") for item in items]

        for race in [row for row in races if row["cluster"] == cluster]:
            finish = race.get("finish_analysis") or {}
            signature_weight = {
                "strong_finish": 1.0,
                "neutral_finish": 0.72,
                "degraded_finish": 0.35,
            }.get(finish.get("final_attack_signature"), 0.6)
            last_5k_gain = finish.get("last_5k_gain_s_per_km")
            finish_component = (signature_weight + norm(gain_values, last_5k_gain)) / 2.0
            continuity_component = norm(stop_values, race.get("stopped_ratio"), lower_better=True)
            economy_component = norm(eq_hre_values, race.get("equivalent_hr_efficiency"), lower_better=True)
            speed_component = norm(eq_pace_values, race.get("equivalent_pace_s_per_km"), lower_better=True)
            score = 100.0 * (
                0.35 * finish_component
                + 0.25 * continuity_component
                + 0.25 * economy_component
                + 0.15 * speed_component
            )

            race["score_components"] = {
                "finish_component": round(100 * finish_component, 1),
                "continuity_component": round(100 * continuity_component, 1),
                "economy_component": round(100 * economy_component, 1),
                "speed_component": round(100 * speed_component, 1),
            }
            race["performance_execution_index"] = round(score, 1)
            race["score_band"] = band_for_score(score)

    last_10 = races[-10:]
    current_name = last_10[-1]["name"] if last_10 else None
    ranked = sorted(last_10, key=lambda row: row["performance_execution_index"], reverse=True)
    rank_map = {row["name"]: idx + 1 for idx, row in enumerate(ranked)}

    entries: list[dict[str, Any]] = []
    for race in last_10:
        fit = race.get("fit_summary") or {}
        finish = race.get("finish_analysis") or {}
        entry = {
            "date": race.get("date"),
            "name": race.get("name"),
            "category": "trail" if "trail" in (race.get("subtype") or "").lower() else "road",
            "cluster": race.get("cluster"),
            "confidence": race.get("confidence"),
            "elapsed_time": race.get("elapsed_time"),
            "elapsed_hours": format_hours(fit.get("total_elapsed_time_s") or race.get("elapsed_time_seconds")),
            "distance_km": round((fit.get("total_distance_km") or race.get("distance_km") or 0.0), 3),
            "equivalent_distance_km": round(race.get("equivalent_distance_km") or 0.0, 3),
            "avg_hr": fit.get("avg_hr"),
            "official_gain_m_for_index": round(race.get("official_gain_m_for_index") or 0.0, 1),
            "stopped_ratio_pct": format_pct(race.get("stopped_ratio")),
            "finish_signature": finish.get("final_attack_signature"),
            "last_5k_gain_s_per_km": finish.get("last_5k_gain_s_per_km"),
            "performance_execution_index": race.get("performance_execution_index"),
            "score_band": race.get("score_band"),
            "score_components": race.get("score_components"),
            "rank_within_last_10": rank_map[race["name"]],
            "is_current": race.get("name") == current_name,
        }
        entries.append(entry)

    current_entry = next((entry for entry in entries if entry["is_current"]), None)
    best_entry = ranked[0] if ranked else None
    best_trail_entry = max((entry for entry in entries if entry["category"] == "trail"), key=lambda x: x["performance_execution_index"], default=None)

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "index_name": "Indice de Execucao de Prova (IEP-100)",
        "purpose": "Comparar suas ultimas 10 provas sem depender de pace puro, priorizando execucao, fechamento, continuidade e economia equivalente dentro do mesmo tipo de prova.",
        "methodology": {
            "components": {
                "finish": "35% = assinatura final do FIT + variacao do ultimo 5 km",
                "continuity": "25% = menor tempo parado proporcional",
                "economy": "25% = economia equivalente por bpm dentro do mesmo grupo de prova",
                "speed": "15% = velocidade equivalente dentro do mesmo grupo de prova",
            },
            "equivalent_distance_rule": "Trail = distancia FIT + D+ oficial/100. Rua = distancia FIT.",
            "clusters": ["road_short", "road_half", "road_long", "trail_mid", "trail_ultra"],
            "confidence_rule": "Portela foi mantida no recorte das ultimas 10, mas marcada como baixa confianca.",
        },
        "entries": entries,
        "summary": {
            "current_race": current_entry,
            "best_overall_last_10": {
                "date": best_entry.get("date") if best_entry else None,
                "name": best_entry.get("name") if best_entry else None,
                "score": best_entry.get("performance_execution_index") if best_entry else None,
            },
            "best_trail_last_10": best_trail_entry,
            "current_position_summary": [
                "A prova mais recente foi o WTR Rio em 14 de marco de 2026.",
                f"O WTR Rio ficou em {current_entry['rank_within_last_10']}o lugar entre as ultimas 10 provas no IEP-100, com score {current_entry['performance_execution_index']}." if current_entry else "",
                "Entre as provas de trilha desse recorte, o WTR Rio foi a melhor execucao recente." if best_trail_entry and current_entry and best_trail_entry["name"] == current_entry["name"] else "",
                "O melhor score geral do recorte veio do 10 km da Maratona do Rio, mas em um contexto curto de rua e com baixa transferencia direta para Arequipa.",
                "No que mais importa para Arequipa, seu estado atual aparece forte: WTR Rio acima de Campos e Serra em execucao recente, com muito menos tempo total de prova e fechamento muito agressivo.",
            ],
        },
    }

    OUTPUT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Ultimas 10 provas - IEP-100",
        "",
        f"Gerado em: {report['generated_at']}",
        "",
        "## 1. O que e o IEP-100",
        "- IEP-100 = Indice de Execucao de Prova.",
        "- Ele nao mede VO2, nem ranking oficial de corrida, nem pace puro.",
        "- Ele foi feito para o seu contexto: completar bem, sustentar endurance e chegar ao fim ainda funcional.",
        "",
        "## 2. Como o indice foi calculado",
        "- 35% fechamento: assinatura final do FIT + variacao do ultimo 5 km.",
        "- 25% continuidade: quanto menos tempo parado proporcional, melhor.",
        "- 25% economia equivalente: pace equivalente por bpm dentro do mesmo tipo de prova.",
        "- 15% velocidade equivalente: pace equivalente dentro do mesmo tipo de prova.",
        "- Trail usa distancia equivalente = distancia FIT + D+ oficial/100.",
        "- Rua usa distancia FIT; D+ de rua nao foi usado como base forte do indice.",
        "",
        "## 3. Leitura principal",
    ]
    for line in report["summary"]["current_position_summary"]:
        if line:
            md_lines.append(f"- {line}")
    md_lines.extend([
        "",
        "## 4. Ultimas 10 provas",
        "| Data | Prova | Cluster | Tempo | IEP-100 | Faixa | Confianca |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for entry in entries:
        md_lines.append(
            f"| {entry['date']} | {entry['name']} | {entry['cluster']} | {entry['elapsed_time']} | {entry['performance_execution_index']} | {entry['score_band']} | {entry['confidence']} |"
        )
    md_lines.extend([
        "",
        "## 5. O que isso diz sobre onde voce esta agora",
        f"- Sua prova mais recente, WTR Rio, entrou com IEP-100 {current_entry['performance_execution_index']} e ficou em {current_entry['rank_within_last_10']}o lugar entre as ultimas 10." if current_entry else "",
        "- Isso coloca seu estado atual acima das suas ultimas ultras trail em execucao pura, principalmente porque o fechamento do WTR Rio foi muito forte.",
        "- Arraial aparece la embaixo porque o fechamento degradou bastante.",
        "- Campos e Serra continuam enormes como benchmarks de montanha longa, mas no recorte estrito de execucao recente o Rio saiu mais limpo.",
        "- Portela segue marcada como baixa confianca e nao deve virar benchmark de performance.",
        "",
        "## 6. Grafico",
        f"- Grafico SVG salvo em: {OUTPUT_SVG_PATH}",
    ])
    OUTPUT_MD_PATH.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    OUTPUT_SVG_PATH.write_text(build_svg(entries), encoding="utf-8")

    print(f"Wrote {OUTPUT_JSON_PATH}")
    print(f"Wrote {OUTPUT_MD_PATH}")
    print(f"Wrote {OUTPUT_SVG_PATH}")


if __name__ == "__main__":
    main()
