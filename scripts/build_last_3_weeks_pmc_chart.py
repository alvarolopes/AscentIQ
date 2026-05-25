from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "performance_management_model.json"
OUT_JSON = ROOT / "analysis" / "context" / "fitness_form_fatigue_last_3_weeks.json"
OUT_MD = ROOT / "analysis" / "context" / "fitness_form_fatigue_last_3_weeks.md"
OUT_SVG = ROOT / "analysis" / "context" / "fitness_form_fatigue_last_3_weeks.svg"


def load_model() -> dict:
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def y_scale(value: float, min_y: float, max_y: float, plot_y: int, plot_h: int) -> float:
    return plot_y + (max_y - value) * plot_h / (max_y - min_y)


def x_scale(index: int, count: int, plot_x: int, plot_w: int) -> float:
    if count <= 1:
        return plot_x
    return plot_x + index * plot_w / (count - 1)


def polyline(rows: list[dict], key: str, color: str, min_y: float, max_y: float, plot_x: int, plot_y: int, plot_w: int, plot_h: int) -> str:
    coords = []
    for index, row in enumerate(rows):
        coords.append(f"{x_scale(index, len(rows), plot_x, plot_w):.1f},{y_scale(row[key], min_y, max_y, plot_y, plot_h):.1f}")
    return f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'


def circle_points(rows: list[dict], key: str, color: str, min_y: float, max_y: float, plot_x: int, plot_y: int, plot_w: int, plot_h: int) -> list[str]:
    out = []
    for index, row in enumerate(rows):
        x = x_scale(index, len(rows), plot_x, plot_w)
        y = y_scale(row[key], min_y, max_y, plot_y, plot_h)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
    return out


def value_labels(rows: list[dict], key: str, color: str, min_y: float, max_y: float, plot_x: int, plot_y: int, plot_w: int, plot_h: int, dy: int) -> list[str]:
    labels = []
    for index, row in enumerate(rows):
        x = x_scale(index, len(rows), plot_x, plot_w)
        y = y_scale(row[key], min_y, max_y, plot_y, plot_h) + dy
        anchor = "middle"
        if index == 0:
            anchor = "start"
        elif index == len(rows) - 1:
            anchor = "end"
        labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="Segoe UI, Arial, sans-serif" font-size="12" font-weight="700" fill="{color}">{row[key]}</text>'
        )
    return labels


def build_svg(rows: list[dict], summary: dict) -> str:
    width, height = 1420, 840
    plot_x, plot_y, plot_w, plot_h = 90, 180, 1220, 470
    fitness_c = "#2563eb"
    fatigue_c = "#ea580c"
    form_c = "#16a34a"
    bg = "#f8fafc"
    text = "#111827"
    muted = "#64748b"
    grid = "#dbe3ee"
    card = "#ffffff"

    values = []
    for row in rows:
        values.extend([row["fitness"], row["fatigue"], row["form"]])
    min_y = min(min(values) - 8, -35)
    max_y = max(max(values) + 8, 100)
    zero_y = y_scale(0, min_y, max_y, plot_y, plot_h)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
        f'<rect x="38" y="36" width="1344" height="760" rx="18" fill="{card}" stroke="#d7dde7" stroke-width="2"/>',
        f'<text x="72" y="88" font-family="Segoe UI, Arial, sans-serif" font-size="34" font-weight="700" fill="{text}">Fitness, Fatigue e Form - ultimas 3 semanas</text>',
        f'<text x="72" y="120" font-family="Segoe UI, Arial, sans-serif" font-size="17" fill="{muted}">Serie diaria do modelo de carga ate {summary["latest_date"]}. Descanso aparece como carga zero no dia.</text>',
    ]

    for line_value in [-30, -15, 0, 25, 50, 75, 100]:
        if min_y <= line_value <= max_y:
            y = y_scale(line_value, min_y, max_y, plot_y, plot_h)
            stroke = "#9ca3af" if line_value == 0 else grid
            width_line = 2 if line_value == 0 else 1
            svg.append(f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" stroke="{stroke}" stroke-width="{width_line}"/>')
            svg.append(f'<text x="48" y="{y + 5:.1f}" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="{muted}">{line_value}</text>')

    svg.append(polyline(rows, "fitness", fitness_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.append(polyline(rows, "fatigue", fatigue_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.append(polyline(rows, "form", form_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.extend(circle_points(rows, "fitness", fitness_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.extend(circle_points(rows, "fatigue", fatigue_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.extend(circle_points(rows, "form", form_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h))
    svg.extend(value_labels(rows, "fitness", fitness_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h, -10))
    svg.extend(value_labels(rows, "fatigue", fatigue_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h, 20))
    svg.extend(value_labels(rows, "form", form_c, min_y, max_y, plot_x, plot_y, plot_w, plot_h, -14))

    for index, row in enumerate(rows):
        if index % 2 == 0 or index == len(rows) - 1:
            x = x_scale(index, len(rows), plot_x, plot_w)
            label = row["date"][5:]
            svg.append(f'<text x="{x:.1f}" y="690" transform="rotate(45 {x:.1f},690)" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="{muted}">{label}</text>')

    latest = rows[-1]
    cards = [
        ("Fitness", latest["fitness"], fitness_c),
        ("Fatigue", latest["fatigue"], fatigue_c),
        ("Form", latest["form"], form_c),
    ]
    for index, (label, value, color) in enumerate(cards):
        x = 78 + index * 250
        svg.append(f'<rect x="{x}" y="720" width="210" height="50" rx="10" fill="#f8fafc" stroke="#e2e8f0"/>')
        svg.append(f'<text x="{x + 18}" y="752" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="{muted}">{label}</text>')
        svg.append(f'<text x="{x + 128}" y="753" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="700" fill="{color}">{value}</text>')

    svg.append(f'<circle cx="980" cy="744" r="7" fill="{fitness_c}"/><text x="996" y="750" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{muted}">Fitness</text>')
    svg.append(f'<circle cx="1085" cy="744" r="7" fill="{fatigue_c}"/><text x="1101" y="750" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{muted}">Fatigue</text>')
    svg.append(f'<circle cx="1195" cy="744" r="7" fill="{form_c}"/><text x="1211" y="750" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{muted}">Form</text>')
    svg.append("</svg>")
    return "\n".join(svg)


def write_markdown(rows: list[dict], summary: dict) -> None:
    latest = rows[-1]
    previous = rows[0]
    md = [
        "# Fitness, Fatigue e Form - ultimas 3 semanas",
        "",
        f"Data final: {summary['latest_date']}",
        "",
        "## Valores atuais",
        f"- Fitness: {latest['fitness']}",
        f"- Fatigue: {latest['fatigue']}",
        f"- Form: {latest['form']}",
        f"- Recovery: {summary.get('recovery', {}).get('score')} ({summary.get('recovery', {}).get('status')})",
        "",
        "## Variacao no periodo",
        f"- Fitness: {previous['fitness']} -> {latest['fitness']} ({round(latest['fitness'] - previous['fitness'], 1)})",
        f"- Fatigue: {previous['fatigue']} -> {latest['fatigue']} ({round(latest['fatigue'] - previous['fatigue'], 1)})",
        f"- Form: {previous['form']} -> {latest['form']} ({round(latest['form'] - previous['form'], 1)})",
        "",
        "## Serie diaria",
        "| Data | Load | Fitness | Fatigue | Form |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(f"| {row['date']} | {row['daily_load']} | {row['fitness']} | {row['fatigue']} | {row['form']} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    model = load_model()
    rows = model["daily_series"][-21:]
    summary = model["summary"]
    OUT_JSON.write_text(json.dumps({"summary": summary, "daily_series": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_SVG.write_text(build_svg(rows, summary), encoding="utf-8")
    write_markdown(rows, summary)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
