from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANALYSIS_CONTEXT_DIR = ROOT / "analysis" / "context"
RACE_INDEX = ROOT / "analysis" / "races" / "last_10_race_performance_index.json"
LONG_INDEX = ROOT / "analysis" / "trainings" / "last_10_long_runs_execution_index.json"
VERT_INDEX = ROOT / "analysis" / "trainings" / "last_10_vertical_sessions_execution_index.json"

OUT_JSON = DATA_DIR / "current_performance_dashboard.json"
OUT_MD = ANALYSIS_CONTEXT_DIR / "current_performance_dashboard.md"
OUT_SVG = ANALYSIS_CONTEXT_DIR / "current_performance_dashboard.svg"

BG = "#f7f4ed"
CARD = "#fffdf8"
TEXT = "#1f1c17"
SUBTEXT = "#5b5449"
BORDER = "#d8d1c4"
RACE_COLOR = "#d97706"
LONG_COLOR = "#0f766e"
VERT_COLOR = "#2f7d32"
ACCENT = "#c2410c"
MUTED = "#b8b0a3"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def score_band(score: float) -> str:
    if score >= 75:
        return "forte"
    if score >= 60:
        return "boa base"
    if score >= 45:
        return "misto"
    return "fragil"


def short_name(name: str) -> str:
    mapping = {
        "WTR Floresta da Tijuca": "WTR Rio",
        "27Â° Meia Maratona Internacional do Rio de Janeiro": "27 Meia",
        "27° Meia Maratona Internacional do Rio de Janeiro": "27 Meia",
        "WTR Campos do JordÃ£o - Ultramaratona 49km": "Campos",
        "WTR Campos do Jordão - Ultramaratona 49km": "Campos",
        "WTR Serra do mar - Ultra": "Serra",
        "Looooooong run": "Looooooong",
        "Pedra da Gavea. Na chuva": "Pedra da Gavea",
        "Run to the hills - Vista chinesa": "Vista chinesa",
    }
    return mapping.get(name, name)


def ratio_pct(current: float, best: float) -> float:
    if not best:
        return 0.0
    return round(100.0 * current / best, 1)


def bar(svg: list[str], x: int, y: int, width: int, height: int, value: float, color: str) -> None:
    svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="#ece7dc"/>')
    fill = max(0.0, min(width, width * value / 100.0))
    svg.append(f'<rect x="{x}" y="{y}" width="{fill:.1f}" height="{height}" rx="8" fill="{color}"/>')


def build_svg(panel: dict[str, Any]) -> str:
    width = 1420
    height = 920
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="70" y="52" font-size="34" font-family="Georgia, serif" fill="{TEXT}" font-weight="700">Painel Atual de Performance</text>',
        f'<text x="70" y="82" font-size="17" font-family="Verdana, sans-serif" fill="{SUBTEXT}">Provas, longoes e vertical em uma unica leitura para Arequipa.</text>',
    ]

    snapshot = panel["arequipa_snapshot"]
    svg.append(f'<rect x="70" y="120" width="320" height="220" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>')
    svg.append(f'<text x="98" y="160" font-size="18" font-family="Verdana, sans-serif" fill="{SUBTEXT}">Snapshot Arequipa</text>')
    svg.append(f'<text x="98" y="245" font-size="78" font-family="Verdana, sans-serif" fill="{ACCENT}" font-weight="700">{snapshot["score"]:.1f}</text>')
    svg.append(f'<text x="245" y="245" font-size="28" font-family="Verdana, sans-serif" fill="{SUBTEXT}">/100</text>')
    svg.append(f'<text x="98" y="285" font-size="22" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">{snapshot["band"]}</text>')
    svg.append(f'<text x="98" y="315" font-size="15" font-family="Verdana, sans-serif" fill="{SUBTEXT}">peso: 40% vertical, 35% prova trail, 25% longao</text>')

    card_specs = [
        ("Prova atual", panel["pillars"]["race"], 430, RACE_COLOR),
        ("Longao atual", panel["pillars"]["long"], 745, LONG_COLOR),
        ("Vertical atual", panel["pillars"]["vertical"], 1060, VERT_COLOR),
    ]
    for title, item, x, color in card_specs:
        svg.append(f'<rect x="{x}" y="120" width="285" height="220" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>')
        svg.append(f'<text x="{x + 24}" y="160" font-size="18" font-family="Verdana, sans-serif" fill="{SUBTEXT}">{title}</text>')
        svg.append(f'<text x="{x + 24}" y="200" font-size="22" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">{short_name(item["name"])}</text>')
        svg.append(f'<text x="{x + 24}" y="248" font-size="62" font-family="Verdana, sans-serif" fill="{color}" font-weight="700">{item["score"]:.1f}</text>')
        svg.append(f'<text x="{x + 165}" y="248" font-size="24" font-family="Verdana, sans-serif" fill="{SUBTEXT}">/100</text>')
        svg.append(f'<text x="{x + 24}" y="282" font-size="15" font-family="Verdana, sans-serif" fill="{SUBTEXT}">rank {item["rank"]}/10 | {item["date"]}</text>')
        svg.append(f'<text x="{x + 24}" y="308" font-size="15" font-family="Verdana, sans-serif" fill="{SUBTEXT}">melhor recente: {short_name(item["best_name"])} ({item["best_score"]:.1f})</text>')
        svg.append(f'<text x="{x + 24}" y="332" font-size="15" font-family="Verdana, sans-serif" fill="{TEXT}">voce esta em {item["relative_to_best_pct"]:.1f}% do seu melhor recente</text>')

    svg.append(f'<rect x="70" y="380" width="1275" height="220" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>')
    svg.append(f'<text x="98" y="420" font-size="22" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">Aderencia ao melhor recente</text>')
    svg.append(f'<text x="98" y="447" font-size="15" font-family="Verdana, sans-serif" fill="{SUBTEXT}">O melhor referente de prova aqui e a melhor trilha recente, nao o 10 km de rua.</text>')

    bars = [
        ("Prova trail", panel["pillars"]["race"]["relative_to_best_pct"], RACE_COLOR, 470),
        ("Longao", panel["pillars"]["long"]["relative_to_best_pct"], LONG_COLOR, 525),
        ("Vertical", panel["pillars"]["vertical"]["relative_to_best_pct"], VERT_COLOR, 580),
    ]
    for label, value, color, y in bars:
        svg.append(f'<text x="98" y="{y - 8}" font-size="18" font-family="Verdana, sans-serif" fill="{TEXT}">{label}</text>')
        bar(svg, 220, y - 24, 980, 22, value, color)
        svg.append(f'<text x="1215" y="{y - 6}" font-size="18" font-family="Verdana, sans-serif" fill="{TEXT}" text-anchor="end">{value:.1f}%</text>')

    svg.append(f'<rect x="70" y="640" width="1275" height="200" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>')
    svg.append(f'<text x="98" y="680" font-size="22" font-family="Verdana, sans-serif" fill="{TEXT}" font-weight="700">Leitura pratica</text>')
    for idx, line in enumerate(panel["messages"]):
        y = 720 + idx * 28
        svg.append(f'<text x="110" y="{y}" font-size="17" font-family="Verdana, sans-serif" fill="{TEXT}">• {line}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


def main() -> None:
    race = load_json(RACE_INDEX)
    long = load_json(LONG_INDEX)
    vertical = load_json(VERT_INDEX)

    race_current = race["summary"]["current_race"]
    race_best = race["summary"].get("best_trail_last_10") or race["summary"]["best_overall_last_10"]
    long_current = long["summary"]["current"]
    long_best_entry = max(long["entries"], key=lambda item: item["score"])
    vert_current = vertical["summary"]["current"]
    vert_best_entry = max(vertical["entries"], key=lambda item: item["score"])

    pillars = {
        "race": {
            "name": race_current["name"],
            "score": race_current["performance_execution_index"],
            "rank": race_current["rank_within_last_10"],
            "date": race_current["date"],
            "best_name": race_best["name"],
            "best_score": race_best["performance_execution_index"],
            "relative_to_best_pct": ratio_pct(race_current["performance_execution_index"], race_best["performance_execution_index"]),
        },
        "long": {
            "name": long_current["name"],
            "score": long_current["score"],
            "rank": long_current["rank"],
            "date": long_current["date"],
            "best_name": long_best_entry["name"],
            "best_score": long_best_entry["score"],
            "relative_to_best_pct": ratio_pct(long_current["score"], long_best_entry["score"]),
        },
        "vertical": {
            "name": vert_current["name"],
            "score": vert_current["score"],
            "rank": vert_current["rank"],
            "date": vert_current["date"],
            "best_name": vert_best_entry["name"],
            "best_score": vert_best_entry["score"],
            "relative_to_best_pct": ratio_pct(vert_current["score"], vert_best_entry["score"]),
        },
    }

    snapshot_score = round(
        pillars["vertical"]["score"] * 0.40
        + pillars["race"]["score"] * 0.35
        + pillars["long"]["score"] * 0.25,
        1,
    )
    snapshot = {
        "score": snapshot_score,
        "band": score_band(snapshot_score),
        "weights": {
            "vertical": 0.40,
            "race": 0.35,
            "long": 0.25,
        },
    }

    messages = [
        f"Seu estado atual de prova esta forte: {short_name(pillars['race']['name'])} entregou {pillars['race']['score']:.1f} e e o seu melhor benchmark trail recente.",
        f"Seu fundo recente tambem esta forte: {short_name(pillars['long']['name'])} chegou a {pillars['long']['score']:.1f}, muito perto do melhor longao recente.",
        f"O gargalo esta claro na vertical: {short_name(pillars['vertical']['name'])} esta em {pillars['vertical']['relative_to_best_pct']:.1f}% do seu melhor vertical recente.",
        "Traduzindo para Arequipa: motor e endurance estao vivos, mas a especificidade de subida ainda esta atrasada em relacao ao seu proprio historico.",
        "Se voce mantiver o fundo e elevar a vertical nas proximas semanas, o painel deve subir rapido sem precisar reinventar sua base aerobica.",
    ]

    dashboard = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "panel_name": "Current Performance Dashboard",
        "purpose": "Juntar prova, longao e vertical em uma leitura unica do momento atual para Arequipa.",
        "pillars": pillars,
        "arequipa_snapshot": snapshot,
        "messages": messages,
        "notes": {
            "composite_score_note": "O Snapshot Arequipa e um resumo ponderado do painel. Ele nao substitui os indices individuais.",
            "race_reference_note": "A referencia de prova usada no painel e a melhor trilha recente, nao a melhor prova curta de rua.",
        },
    }

    md_lines = [
        "# Current Performance Dashboard",
        "",
        f"Gerado em: {dashboard['generated_at']}",
        "",
        "## 1. Snapshot Arequipa",
        f"- Score composto atual: {snapshot['score']}/100",
        f"- Faixa: {snapshot['band']}",
        "- Peso do snapshot: 40% vertical, 35% prova trail, 25% longao.",
        "- Nota: esse score e um resumo do painel, nao substitui os indices individuais.",
        "",
        "## 2. Pilares atuais",
        f"- Prova atual: {pillars['race']['name']} ({pillars['race']['date']}) | {pillars['race']['score']}/100 | rank {pillars['race']['rank']}/10 | {pillars['race']['relative_to_best_pct']}% do melhor trail recente.",
        f"- Longao atual: {pillars['long']['name']} ({pillars['long']['date']}) | {pillars['long']['score']}/100 | rank {pillars['long']['rank']}/10 | {pillars['long']['relative_to_best_pct']}% do melhor longao recente.",
        f"- Vertical atual: {pillars['vertical']['name']} ({pillars['vertical']['date']}) | {pillars['vertical']['score']}/100 | rank {pillars['vertical']['rank']}/10 | {pillars['vertical']['relative_to_best_pct']}% do melhor vertical recente.",
        "",
        "## 3. Leitura pratica",
    ]
    for line in messages:
        md_lines.append(f"- {line}")
    md_lines.extend([
        "",
        "## 4. Leitura de treinador",
        "- Se eu resumir em uma frase: voce esta pronto em motor e fundo, mas ainda abaixo do seu melhor padrao de subida especifica.",
        "- O WTR Rio mostrou prova forte e funcional no final.",
        "- Bravado mostrou longao recente forte.",
        "- O mesmo Bravado, quando lido como sessao vertical, mostrou que a subida atual ainda esta longe do seu melhor bloco de 2025.",
        "",
        "## 5. Arquivos-base",
        f"- Provas: {RACE_INDEX.name}",
        f"- Longoes: {LONG_INDEX.name}",
        f"- Verticais: {VERT_INDEX.name}",
        f"- Painel SVG: {OUT_SVG}",
    ])

    OUT_JSON.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    OUT_SVG.write_text(build_svg(dashboard), encoding="utf-8")

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_SVG}")


if __name__ == "__main__":
    main()
