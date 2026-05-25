from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANALYSIS_DIR = ROOT / "analysis" / "trainings"
MASTER_INDEX_PATH = DATA_DIR / "activity_master_index.json"

LONG_JSON = ANALYSIS_DIR / "last_10_long_runs_execution_index.json"
LONG_MD = ANALYSIS_DIR / "last_10_long_runs_execution_index.md"
LONG_SVG = ANALYSIS_DIR / "last_10_long_runs_execution_chart.svg"
VERT_JSON = ANALYSIS_DIR / "last_10_vertical_sessions_execution_index.json"
VERT_MD = ANALYSIS_DIR / "last_10_vertical_sessions_execution_index.md"
VERT_SVG = ANALYSIS_DIR / "last_10_vertical_sessions_execution_chart.svg"
OVERVIEW_MD = ANALYSIS_DIR / "training_execution_indexes_overview.md"

BG = "#f7f4ed"
GRID = "#d6d0c3"
TEXT = "#1f1c17"
SUBTEXT = "#5b5449"
COLOR_RUN = "#1f5aa6"
COLOR_HIKE = "#7d5a27"
COLOR_CURRENT = "#d9480f"
COLOR_LONG = "#0f766e"
COLOR_VERTICAL = "#2f7d32"

SHORT_LABELS = {
    "Primeira Volta internacional do dia do amigo": "Dia do amigo",
    "Morning Run": "Morning",
    "Evening Run": "Evening",
    "Longing": "Longing",
    "Afternoon Run": "Afternoon",
    "Looooooong run": "Looooong",
    "May the forth be with us": "May the forth",
    "Treino regenerativo com foco em lesão": "Regenerativo",
    "Bravado": "Bravado",
    "Run to the hills - Vista chinesa": "Vista chinesa",
    "Pedra da Gavea. Na chuva": "Pedra da Gavea",
    "O Salto": "O Salto",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def stopped_ratio(activity: dict[str, Any]) -> float:
    fit = activity.get("fit_summary") or {}
    elapsed = fit.get("total_elapsed_time_s") or 0.0
    if not elapsed:
        return 0.0
    return (fit.get("stopped_time_s") or 0.0) / elapsed


def finish_weight(signature: str | None) -> float:
    return {
        "strong_finish": 1.0,
        "neutral_finish": 0.72,
        "degraded_finish": 0.35,
    }.get(signature, 0.6)


def short_label(name: str) -> str:
    return SHORT_LABELS.get(name, name)


def score_band(score: float) -> str:
    if score >= 80:
        return "muito forte"
    if score >= 65:
        return "forte"
    if score >= 50:
        return "solida"
    return "abaixo do melhor historico"


def build_svg(entries: list[dict[str, Any]], *, title: str, subtitle: str, time_label: str, score_label: str, category_colors: dict[str, str], current_name: str, current_key: str) -> str:
    width = 1400
    height = 900
    margin_left = 90
    margin_right = 40
    top_chart_top = 95
    top_chart_height = 250
    bottom_chart_top = 470
    bottom_chart_height = 250
    chart_width = width - margin_left - margin_right
    gap = 18
    count = len(entries)
    bar_width = (chart_width - gap * (count - 1)) / count
    max_time = max(entry["elapsed_hours"] for entry in entries if entry["elapsed_hours"] is not None)

    def x_for(index: int) -> float:
        return margin_left + index * (bar_width + gap)

    def top_y(value: float) -> float:
        usable = top_chart_height - 10
        return top_chart_top + top_chart_height - (value / max_time) * usable

    def bottom_y(value: float) -> float:
        usable = bottom_chart_height - 10
        return bottom_chart_top + bottom_chart_height - (value / 100.0) * usable

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="{margin_left}" y="45" font-size="32" font-family="Georgia, serif" fill="{TEXT}" font-weight="700">{title}</text>',
        f'<text x="{margin_left}" y="72" font-size="16" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{subtitle}</text>',
    ]

    step = 2 if max_time > 6 else 1
    for marker in range(0, int(max_time) + step + 1, step):
        y = top_y(marker)
        parts.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 5:.1f}" text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{marker}h</text>')

    for marker in range(0, 101, 20):
        y = bottom_y(marker)
        parts.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 5:.1f}" text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{marker}</text>')

    parts.append(f'<text x="{margin_left}" y="{top_chart_top - 22}" font-size="20" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">{time_label}</text>')
    parts.append(f'<text x="{margin_left}" y="{bottom_chart_top - 22}" font-size="20" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">{score_label}</text>')

    for idx, entry in enumerate(entries):
        x = x_for(idx)
        color = category_colors.get(entry[current_key], COLOR_LONG)
        stroke = COLOR_CURRENT if entry["name"] == current_name else "none"
        stroke_width = 4 if entry["name"] == current_name else 0
        top = top_y(entry["elapsed_hours"])
        top_height = top_chart_top + top_chart_height - top
        bottom = bottom_y(entry["score"])
        bottom_height = bottom_chart_top + bottom_chart_height - bottom
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_width:.1f}" height="{top_height:.1f}" rx="6" fill="{color}" opacity="0.85" stroke="{stroke}" stroke-width="{stroke_width}"/>')
        parts.append(f'<rect x="{x:.1f}" y="{bottom:.1f}" width="{bar_width:.1f}" height="{bottom_height:.1f}" rx="6" fill="{color}" opacity="0.85" stroke="{stroke}" stroke-width="{stroke_width}"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{top - 8:.1f}" text-anchor="middle" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{entry['elapsed_hours']:.2f}h</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{bottom - 8:.1f}" text-anchor="middle" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{entry['score']:.1f}</text>')
        label_x = x + bar_width / 2
        label_y = bottom_chart_top + bottom_chart_height + 86
        label = f"{entry['date'][5:]} | {short_label(entry['name'])}"
        parts.append(f'<g transform="translate({label_x:.1f},{label_y:.1f}) rotate(-32)">')
        parts.append(f'<text text-anchor="end" font-size="13" font-family="Verdana, sans-serif" fill="{TEXT}">{label}</text>')
        parts.append('</g>')

    legend_y = 808
    legend_x = margin_left
    for key, label in [(k, k) for k in category_colors.keys()]:
        fill = category_colors[key]
        label_text = 'Run' if key == 'Run' else ('Hike/Walk' if key == 'Hike/Walk' else key)
        parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="18" height="18" fill="{fill}" opacity="0.85"/>')
        parts.append(f'<text x="{legend_x + 28}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">{label_text}</text>')
        legend_x += 120
    parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="18" height="18" fill="white" stroke="{COLOR_CURRENT}" stroke-width="3"/>')
    parts.append(f'<text x="{legend_x + 28}" y="{legend_y + 14}" font-size="14" font-family="Verdana, sans-serif" fill="{TEXT}">Treino mais recente</text>')
    parts.append(f'<text x="{margin_left}" y="{legend_y + 42}" font-size="13" font-family="Verdana, sans-serif" fill="{SUBTEXT}">Cronologia da esquerda para a direita.</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def build_long_index(activities: list[dict[str, Any]]) -> dict[str, Any]:
    long_runs = []
    for activity in activities:
        if activity.get("activity_type") != "Run" or activity.get("is_race_candidate"):
            continue
        fit = activity.get("fit_summary") or {}
        distance = fit.get("total_distance_km") or activity.get("distance_km") or 0.0
        if distance < 20:
            continue
        ascent = fit.get("total_ascent_m") or activity.get("elevation_gain_m") or 0.0
        equivalent_distance = distance + ascent / 100.0
        work_time_s = fit.get("total_timer_time_s") or activity.get("moving_time_seconds") or fit.get("total_elapsed_time_s") or activity.get("elapsed_time_seconds") or 0.0
        equivalent_pace = (work_time_s / equivalent_distance) if equivalent_distance else None
        avg_hr = fit.get("avg_hr")
        equivalent_hr_efficiency = (equivalent_pace / avg_hr) if avg_hr else None
        long_runs.append({
            **activity,
            "equivalent_distance_km": equivalent_distance,
            "equivalent_pace_s_per_km": equivalent_pace,
            "equivalent_hr_efficiency": equivalent_hr_efficiency,
            "stopped_ratio": stopped_ratio(activity),
        })

    long_runs.sort(key=lambda row: (row.get("date", ""), row.get("date_time", "")))
    baseline = long_runs
    eq_pace_values = [row.get("equivalent_pace_s_per_km") for row in baseline]
    eq_hre_values = [row.get("equivalent_hr_efficiency") for row in baseline]
    stop_values = [row.get("stopped_ratio") for row in baseline]
    gain_values = [(row.get("finish_analysis") or {}).get("last_5k_gain_s_per_km") for row in baseline]

    for row in long_runs:
        finish = row.get("finish_analysis") or {}
        finish_component = (
            finish_weight(finish.get("final_attack_signature"))
            + norm(gain_values, finish.get("last_5k_gain_s_per_km"))
        ) / 2.0
        continuity_component = norm(stop_values, row.get("stopped_ratio"), lower_better=True)
        economy_component = norm(eq_hre_values, row.get("equivalent_hr_efficiency"), lower_better=True)
        speed_component = norm(eq_pace_values, row.get("equivalent_pace_s_per_km"), lower_better=True)
        score = 100.0 * (
            0.35 * finish_component
            + 0.25 * continuity_component
            + 0.25 * economy_component
            + 0.15 * speed_component
        )
        row["execution_score"] = round(score, 1)
        row["score_components"] = {
            "finish_component": round(100 * finish_component, 1),
            "continuity_component": round(100 * continuity_component, 1),
            "economy_component": round(100 * economy_component, 1),
            "speed_component": round(100 * speed_component, 1),
        }

    last_10 = long_runs[-10:]
    ranked = sorted(last_10, key=lambda row: row["execution_score"], reverse=True)
    rank_map = {row["name"] + row["date"]: idx + 1 for idx, row in enumerate(ranked)}
    entries = []
    for row in last_10:
        fit = row.get("fit_summary") or {}
        key = row["name"] + row["date"]
        entries.append({
            "date": row.get("date"),
            "name": row.get("name"),
            "elapsed_time": row.get("moving_time") or row.get("elapsed_time"),
            "elapsed_hours": round((fit.get("total_timer_time_s") or row.get("moving_time_seconds") or fit.get("total_elapsed_time_s") or row.get("elapsed_time_seconds") or 0.0) / 3600.0, 2),
            "distance_km": round((fit.get("total_distance_km") or row.get("distance_km") or 0.0), 2),
            "ascent_m": round((fit.get("total_ascent_m") or row.get("elevation_gain_m") or 0.0), 1),
            "equivalent_distance_km": round(row.get("equivalent_distance_km") or 0.0, 2),
            "avg_hr": fit.get("avg_hr"),
            "score": row.get("execution_score"),
            "band": score_band(row.get("execution_score") or 0.0),
            "finish_signature": (row.get("finish_analysis") or {}).get("final_attack_signature"),
            "stopped_ratio_pct": round(100 * row.get("stopped_ratio", 0.0), 1),
            "score_components": row.get("score_components"),
            "rank": rank_map[key],
            "modality": row.get("activity_type"),
        })

    current = entries[-1] if entries else None
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "index_name": "IEL-100",
        "full_name": "Indice de Execucao de Longao",
        "methodology": {
            "finish": "35% = assinatura final do FIT + variacao do ultimo 5 km",
            "continuity": "25% = menor tempo parado proporcional",
            "economy": "25% = pace equivalente por bpm",
            "speed": "15% = pace equivalente",
            "equivalent_distance_rule": "distancia FIT + D+ FIT/100",
        },
        "entries": entries,
        "summary": {
            "current": current,
            "best": ranked[0]["name"] if ranked else None,
            "current_summary": [
                f"O longao mais recente foi {current['name']} em {current['date']}." if current else "",
                f"Ele entrou com IEL-100 {current['score']} e ficou em {current['rank']}o entre os ultimos 10 longoes." if current else "",
                "Isso indica que sua base longa atual esta boa e bem executada." if current and current["rank"] <= 3 else "",
                "O IEL-100 de longao mede execucao de endurance e nao especificidade vertical maxima." if current else "",
            ],
        },
    }


def build_vertical_index(activities: list[dict[str, Any]]) -> dict[str, Any]:
    verticals = []
    for activity in activities:
        if activity.get("is_race_candidate") or activity.get("activity_type") not in {"Run", "Hike", "Walk"}:
            continue
        fit = activity.get("fit_summary") or {}
        ascent = fit.get("total_ascent_m") or activity.get("elevation_gain_m") or 0.0
        if ascent < 500:
            continue
        work_time_s = fit.get("total_timer_time_s") or activity.get("moving_time_seconds") or fit.get("total_elapsed_time_s") or activity.get("elapsed_time_seconds") or 0.0
        vertical_speed = (ascent / (work_time_s / 3600.0)) if work_time_s else None
        avg_hr = fit.get("avg_hr")
        vertical_efficiency = (vertical_speed / avg_hr) if vertical_speed and avg_hr else None
        modality_group = "Run" if activity.get("activity_type") == "Run" else "Hike/Walk"
        verticals.append({
            **activity,
            "vertical_speed_m_per_h": vertical_speed,
            "vertical_efficiency": vertical_efficiency,
            "stopped_ratio": stopped_ratio(activity),
            "modality_group": modality_group,
        })

    verticals.sort(key=lambda row: (row.get("date", ""), row.get("date_time", "")))
    for modality in {"Run", "Hike/Walk"}:
        bucket = [row for row in verticals if row["modality_group"] == modality]
        output_values = [row.get("vertical_speed_m_per_h") for row in bucket]
        eco_values = [row.get("vertical_efficiency") for row in bucket]
        stop_values = [row.get("stopped_ratio") for row in bucket]
        gain_values = [(row.get("finish_analysis") or {}).get("last_2k_gain_s_per_km") for row in bucket]
        for row in bucket:
            finish = row.get("finish_analysis") or {}
            finish_component = (
                finish_weight(finish.get("final_attack_signature"))
                + norm(gain_values, finish.get("last_2k_gain_s_per_km"))
            ) / 2.0
            continuity_component = norm(stop_values, row.get("stopped_ratio"), lower_better=True)
            output_component = norm(output_values, row.get("vertical_speed_m_per_h"))
            economy_component = norm(eco_values, row.get("vertical_efficiency"))
            score = 100.0 * (
                0.35 * output_component
                + 0.30 * economy_component
                + 0.20 * continuity_component
                + 0.15 * finish_component
            )
            row["execution_score"] = round(score, 1)
            row["score_components"] = {
                "output_component": round(100 * output_component, 1),
                "economy_component": round(100 * economy_component, 1),
                "continuity_component": round(100 * continuity_component, 1),
                "finish_component": round(100 * finish_component, 1),
            }

    last_10 = verticals[-10:]
    ranked = sorted(last_10, key=lambda row: row["execution_score"], reverse=True)
    rank_map = {row["name"] + row["date"] + row.get("activity_type", ""): idx + 1 for idx, row in enumerate(ranked)}
    entries = []
    for row in last_10:
        fit = row.get("fit_summary") or {}
        key = row["name"] + row["date"] + row.get("activity_type", "")
        entries.append({
            "date": row.get("date"),
            "name": row.get("name"),
            "activity_type": row.get("activity_type"),
            "modality_group": row.get("modality_group"),
            "elapsed_time": row.get("moving_time") or row.get("elapsed_time"),
            "elapsed_hours": round((fit.get("total_timer_time_s") or row.get("moving_time_seconds") or fit.get("total_elapsed_time_s") or row.get("elapsed_time_seconds") or 0.0) / 3600.0, 2),
            "distance_km": round((fit.get("total_distance_km") or row.get("distance_km") or 0.0), 2),
            "ascent_m": round((fit.get("total_ascent_m") or row.get("elevation_gain_m") or 0.0), 1),
            "avg_hr": fit.get("avg_hr"),
            "vertical_speed_m_per_h": round(row.get("vertical_speed_m_per_h") or 0.0, 1),
            "vertical_efficiency": round(row.get("vertical_efficiency") or 0.0, 3) if row.get("vertical_efficiency") is not None else None,
            "score": row.get("execution_score"),
            "band": score_band(row.get("execution_score") or 0.0),
            "finish_signature": (row.get("finish_analysis") or {}).get("final_attack_signature"),
            "stopped_ratio_pct": round(100 * row.get("stopped_ratio", 0.0), 1),
            "score_components": row.get("score_components"),
            "rank": rank_map[key],
        })

    current = entries[-1] if entries else None
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "index_name": "IEV-100",
        "full_name": "Indice de Execucao Vertical",
        "methodology": {
            "output": "35% = vertical speed (m/h)",
            "economy": "30% = vertical speed por bpm",
            "continuity": "20% = menor tempo parado proporcional",
            "finish": "15% = assinatura final + variacao dos ultimos 2 km",
            "comparison_rule": "Run e Hike/Walk sao comparados dentro da mesma modalidade antes de entrar no ranking final.",
        },
        "entries": entries,
        "summary": {
            "current": current,
            "best": ranked[0]["name"] if ranked else None,
            "current_summary": [
                f"A sessao vertical mais recente foi {current['name']} em {current['date']}." if current else "",
                f"Ela entrou com IEV-100 {current['score']} e ficou em {current['rank']}o entre as ultimas 10 sessoes verticais." if current else "",
                "Isso sugere que sua especificidade vertical atual esta abaixo do seu melhor historico recente." if current and current["rank"] >= 7 else "",
                "No vertical, o indice prioriza montanha: subir bem, com boa economia e pouca quebra." if current else "",
            ],
        },
    }


def render_long_md(report: dict[str, Any]) -> str:
    lines = [
        "# Ultimos 10 longoes - IEL-100",
        "",
        f"Gerado em: {report['generated_at']}",
        "",
        "## 1. O que e o IEL-100",
        "- IEL-100 = Indice de Execucao de Longao.",
        "- Ele compara como o longao foi executado, e nao apenas quanto ele durou.",
        "",
        "## 2. Como foi calculado",
        "- 35% fechamento.",
        "- 25% continuidade.",
        "- 25% economia equivalente por bpm.",
        "- 15% velocidade equivalente.",
        "- Distancia equivalente = distancia FIT + D+ FIT/100.",
        "",
        "## 3. Leitura principal",
    ]
    for line in report["summary"]["current_summary"]:
        if line:
            lines.append(f"- {line}")
    lines.extend([
        "",
        "## 4. Ultimos 10 longoes",
        "| Data | Treino | Tempo ativo | Dist. eq. | IEL-100 | Faixa | Rank |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for entry in report["entries"]:
        lines.append(f"| {entry['date']} | {entry['name']} | {entry['elapsed_time']} | {entry['equivalent_distance_km']:.2f} km | {entry['score']} | {entry['band']} | {entry['rank']} |")
    lines.append("")
    lines.append(f"- Grafico SVG salvo em: {LONG_SVG}")
    return "\n".join(lines) + "\n"


def render_vertical_md(report: dict[str, Any]) -> str:
    lines = [
        "# Ultimas 10 sessoes verticais - IEV-100",
        "",
        f"Gerado em: {report['generated_at']}",
        "",
        "## 1. O que e o IEV-100",
        "- IEV-100 = Indice de Execucao Vertical.",
        "- Ele foi desenhado para montanha: subir bem, com boa economia e pouca quebra.",
        "",
        "## 2. Como foi calculado",
        "- 35% vertical speed.",
        "- 30% eficiencia vertical por bpm.",
        "- 20% continuidade.",
        "- 15% fechamento final.",
        "- Run e Hike/Walk sao comparados dentro da propria modalidade antes de entrar no ranking final.",
        "",
        "## 3. Leitura principal",
    ]
    for line in report["summary"]["current_summary"]:
        if line:
            lines.append(f"- {line}")
    lines.extend([
        "",
        "## 4. Ultimas 10 sessoes verticais",
        "| Data | Treino | Tipo | Tempo ativo | VAM | IEV-100 | Faixa | Rank |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for entry in report["entries"]:
        lines.append(f"| {entry['date']} | {entry['name']} | {entry['activity_type']} | {entry['elapsed_time']} | {entry['vertical_speed_m_per_h']:.1f} | {entry['score']} | {entry['band']} | {entry['rank']} |")
    lines.append("")
    lines.append(f"- Grafico SVG salvo em: {VERT_SVG}")
    return "\n".join(lines) + "\n"


def render_overview(long_report: dict[str, Any], vertical_report: dict[str, Any]) -> str:
    long_current = long_report["summary"]["current"]
    vert_current = vertical_report["summary"]["current"]
    lines = [
        "# Training Execution Indexes Overview",
        "",
        f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 1. Onde voce esta agora",
        f"- Longao atual: {long_current['name']} em {long_current['date']} com IEL-100 {long_current['score']} e rank {long_current['rank']}/10." if long_current else "",
        f"- Vertical atual: {vert_current['name']} em {vert_current['date']} com IEV-100 {vert_current['score']} e rank {vert_current['rank']}/10." if vert_current else "",
        "- Leitura curta: seu longao recente esta forte, mas sua sessao vertical recente esta abaixo do seu melhor historico vertical.",
        "",
        "## 2. Arquivos",
        f"- Longoes: {LONG_MD.name}",
        f"- Grafico dos longoes: {LONG_SVG.name}",
        f"- Verticais: {VERT_MD.name}",
        f"- Grafico das verticais: {VERT_SVG.name}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    activities = load_json(MASTER_INDEX_PATH)
    long_report = build_long_index(activities)
    vertical_report = build_vertical_index(activities)

    LONG_JSON.write_text(json.dumps(long_report, ensure_ascii=False, indent=2), encoding="utf-8")
    VERT_JSON.write_text(json.dumps(vertical_report, ensure_ascii=False, indent=2), encoding="utf-8")
    LONG_MD.write_text(render_long_md(long_report), encoding="utf-8")
    VERT_MD.write_text(render_vertical_md(vertical_report), encoding="utf-8")

    long_current_name = long_report["summary"]["current"]["name"] if long_report["summary"]["current"] else ""
    vertical_current_name = vertical_report["summary"]["current"]["name"] if vertical_report["summary"]["current"] else ""

    LONG_SVG.write_text(
        build_svg(
            long_report["entries"],
            title="Ultimos 10 longoes: tempo e IEL-100",
            subtitle="IEL-100 privilegia execucao de endurance, continuidade e economia equivalente.",
            time_label="Tempo ativo FIT (horas)",
            score_label="IEL-100",
            category_colors={"Run": COLOR_LONG},
            current_name=long_current_name,
            current_key="modality",
        ),
        encoding="utf-8",
    )
    VERT_SVG.write_text(
        build_svg(
            vertical_report["entries"],
            title="Ultimas 10 sessoes verticais: tempo e IEV-100",
            subtitle="IEV-100 privilegia VAM, economia vertical, continuidade e fechamento.",
            time_label="Tempo ativo FIT (horas)",
            score_label="IEV-100",
            category_colors={"Run": COLOR_VERTICAL, "Hike/Walk": COLOR_HIKE},
            current_name=vertical_current_name,
            current_key="modality_group",
        ),
        encoding="utf-8",
    )
    OVERVIEW_MD.write_text(render_overview(long_report, vertical_report), encoding="utf-8")

    print(f"Wrote {LONG_JSON}")
    print(f"Wrote {LONG_MD}")
    print(f"Wrote {LONG_SVG}")
    print(f"Wrote {VERT_JSON}")
    print(f"Wrote {VERT_MD}")
    print(f"Wrote {VERT_SVG}")
    print(f"Wrote {OVERVIEW_MD}")


if __name__ == "__main__":
    main()
