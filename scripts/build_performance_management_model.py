from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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

FITNESS_DAYS = 42
FATIGUE_DAYS = 7
RAMP_DAYS = 7


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


def parse_duration_seconds(value: Any) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
    except ValueError:
        return None
    return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def activity_date(item: dict[str, Any]) -> date | None:
    raw = item.get("date")
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def activity_duration_minutes(item: dict[str, Any]) -> float | None:
    for key in ("duration_seconds", "moving_time_seconds"):
        value = as_float(item.get(key))
        if value and value > 0:
            return value / 60.0
    for key in ("moving_time", "elapsed_time"):
        seconds = parse_duration_seconds(item.get(key))
        if seconds and seconds > 0:
            return seconds / 60.0
    return None


def observed_hr_bounds(activities: list[dict[str, Any]], sleep: dict[str, Any] | None) -> tuple[int, int]:
    resting = None
    if sleep:
        resting = (sleep.get("summary") or {}).get("latest_daily", {}).get("resting_hr")
    max_values = [as_float(item.get("max_hr")) for item in activities]
    max_values = [value for value in max_values if value is not None]
    return int(resting or 54), int(max(max_values + [188]))


def fallback_hrr(item: dict[str, Any]) -> float:
    activity_type = item.get("type")
    cls = item.get("classification_hint")
    if cls == "limiar":
        return 0.72
    if cls == "longao":
        return 0.62
    if cls == "subida especifica":
        return 0.64
    if activity_type == "Weight Training":
        return 0.38
    if activity_type == "Swim":
        return 0.45
    if activity_type == "Walk":
        return 0.28
    return 0.52


def type_multiplier(item: dict[str, Any]) -> float:
    return {
        "Run": 1.0,
        "Hike": 1.08,
        "Stair-Stepper": 1.05,
        "Swim": 0.75,
        "Walk": 0.38,
        "Weight Training": 0.55,
    }.get(item.get("type"), 0.65)


def elevation_gain(item: dict[str, Any]) -> float:
    official = as_float(item.get("official_elevation_gain_m"))
    watch = as_float(item.get("watch_elevation_gain_m"))
    direct = as_float(item.get("elevation_gain_m"))
    if official is not None and official > 0:
        return official
    if watch is not None and watch > 0:
        return watch
    return direct or 0.0


def estimate_activity_load(item: dict[str, Any], resting_hr: int, max_hr: int) -> dict[str, Any] | None:
    minutes = activity_duration_minutes(item)
    if not minutes:
        return None

    avg_hr = as_float(item.get("avg_hr"))
    if avg_hr and max_hr > resting_hr:
        hrr = (avg_hr - resting_hr) / (max_hr - resting_hr)
        hrr_source = "avg_hr"
    else:
        hrr = fallback_hrr(item)
        hrr_source = "fallback_by_type"

    hrr = max(0.18, min(1.05, hrr))
    trimp = minutes * hrr * 0.64 * math.exp(1.92 * hrr)
    vertical_bonus = 0.0
    if item.get("type") in {"Run", "Hike", "Stair-Stepper"}:
        vertical_bonus = elevation_gain(item) / 100.0 * 2.5

    load = trimp * type_multiplier(item) + vertical_bonus
    return {
        "date": item.get("date"),
        "name": item.get("name"),
        "type": item.get("type"),
        "classification_hint": item.get("classification_hint"),
        "duration_min": round(minutes, 1),
        "distance_km": as_float(item.get("distance_km")),
        "avg_hr": avg_hr,
        "elevation_gain_m": round(elevation_gain(item), 1),
        "hrr": round(hrr, 3),
        "hrr_source": hrr_source,
        "estimated_load": round(load, 1),
    }


def collect_activities() -> list[dict[str, Any]]:
    training = load_history(TRAINING_HISTORY_PATH, SAMPLE_TRAINING_HISTORY_PATH)
    races = load_history(RACE_HISTORY_PATH, SAMPLE_RACE_HISTORY_PATH)

    items: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source, rows in (("training_history", training), ("race_history", races)):
        for row in rows:
            day = row.get("date")
            if not day:
                continue
            key = (
                day,
                row.get("type"),
                row.get("name"),
                round(as_float(row.get("distance_km")) or 0, 2),
                row.get("elapsed_time"),
            )
            if key in seen:
                continue
            item = dict(row)
            item["model_source"] = source
            items.append(item)
            seen.add(key)
    items.sort(key=lambda item: (item.get("date") or "", item.get("date_time") or "", item.get("name") or ""))
    return items


def build_daily_loads(activities: list[dict[str, Any]], sleep: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resting_hr, max_hr = observed_hr_bounds(activities, sleep)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in activities:
        day = activity_date(item)
        if not day:
            continue
        load = estimate_activity_load(item, resting_hr, max_hr)
        if load:
            by_day[day.isoformat()].append(load)

    if not by_day:
        return [], {"resting_hr": resting_hr, "max_hr": max_hr}

    start = datetime.strptime(min(by_day), "%Y-%m-%d").date()
    end = max(datetime.strptime(max(by_day), "%Y-%m-%d").date(), datetime.now().date())
    daily: list[dict[str, Any]] = []
    cursor = start
    fitness = 0.0
    fatigue = 0.0

    while cursor <= end:
        key = cursor.isoformat()
        activities_today = by_day.get(key, [])
        load = round(sum(item["estimated_load"] for item in activities_today), 1)
        fitness = fitness + (load - fitness) / FITNESS_DAYS
        fatigue = fatigue + (load - fatigue) / FATIGUE_DAYS
        form = fitness - fatigue
        daily.append(
            {
                "date": key,
                "daily_load": load,
                "fitness": round(fitness, 1),
                "fatigue": round(fatigue, 1),
                "form": round(form, 1),
                "activity_count": len(activities_today),
                "activities": activities_today,
            }
        )
        cursor += timedelta(days=1)

    for index, row in enumerate(daily):
        if index >= RAMP_DAYS:
            row["fitness_ramp_rate_7d"] = round(row["fitness"] - daily[index - RAMP_DAYS]["fitness"], 1)
        else:
            row["fitness_ramp_rate_7d"] = None

    meta = {
        "resting_hr_used": resting_hr,
        "max_hr_used": max_hr,
        "fitness_time_constant_days": FITNESS_DAYS,
        "fatigue_time_constant_days": FATIGUE_DAYS,
        "ramp_window_days": RAMP_DAYS,
        "load_model": "TRIMP-like athlete load with type multiplier and vertical bonus",
    }
    return daily, meta


def form_status(form: float) -> str:
    if form >= 10:
        return "fresh"
    if form >= -10:
        return "balanced"
    if form >= -25:
        return "going_hard"
    return "overloaded"


def ramp_status(ramp: float | None) -> str:
    if ramp is None:
        return "unknown"
    if ramp < -1:
        return "recovering"
    if ramp < 2:
        return "steady"
    if ramp < 5:
        return "building"
    return "going_hard"


def last_n_sum(daily: list[dict[str, Any]], days: int) -> float:
    return round(sum(row["daily_load"] for row in daily[-days:]), 1)


def recovery_status(score: float | None, delta: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 75 and (delta is None or delta >= -5):
        return "good"
    if score >= 67 and (delta is None or delta >= -8):
        return "stable"
    if score >= 60:
        return "watch"
    return "low"


def build_recovery_summary(sleep: dict[str, Any] | None, reference_date: str | None = None) -> dict[str, Any]:
    if not sleep:
        return {"score": None, "status": "unknown", "basis": "none"}

    weekly = sleep.get("weekly") or []
    latest_weekly = (sleep.get("summary") or {}).get("latest_weekly")
    latest_daily = (sleep.get("summary") or {}).get("latest_daily")

    if latest_daily and latest_daily.get("score") is not None:
        use_daily = False
        if reference_date:
            try:
                daily_date = datetime.strptime(latest_daily.get("date"), "%Y-%m-%d").date()
                ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
                use_daily = 0 <= (ref_date - daily_date).days <= 2
            except (TypeError, ValueError):
                use_daily = False
        if use_daily:
            score = latest_daily.get("score")
            return {
                "score": score,
                "status": recovery_status(score, None),
                "basis": "daily_sleep",
                "period": latest_daily.get("date"),
                "quality": latest_daily.get("quality"),
                "duration_minutes": latest_daily.get("duration_minutes"),
                "duration_raw": latest_daily.get("duration_raw"),
                "resting_hr": latest_daily.get("resting_hr"),
                "body_battery": latest_daily.get("body_battery"),
            }

    if latest_weekly and latest_weekly.get("average_score") is not None:
        score = latest_weekly.get("average_score")
        previous = weekly[1].get("average_score") if len(weekly) > 1 else None
        delta = score - previous if previous is not None else None
        return {
            "score": score,
            "status": recovery_status(score, delta),
            "basis": "weekly_sleep",
            "period": latest_weekly.get("period"),
            "quality": latest_weekly.get("average_quality"),
            "duration_minutes": latest_weekly.get("average_duration_minutes"),
            "duration_raw": latest_weekly.get("average_duration_raw"),
            "previous_week_score": previous,
            "score_delta_vs_previous_week": delta,
        }

    if latest_daily and latest_daily.get("score") is not None:
        score = latest_daily.get("score")
        return {
            "score": score,
            "status": recovery_status(score, None),
            "basis": "daily_sleep",
            "period": latest_daily.get("date"),
            "quality": latest_daily.get("quality"),
            "duration_minutes": latest_daily.get("duration_minutes"),
            "duration_raw": latest_daily.get("duration_raw"),
            "resting_hr": latest_daily.get("resting_hr"),
            "body_battery": latest_daily.get("body_battery"),
        }

    return {"score": None, "status": "unknown", "basis": "sleep_without_score"}


def build_summary(daily: list[dict[str, Any]], meta: dict[str, Any], sleep: dict[str, Any] | None) -> dict[str, Any]:
    latest = daily[-1]
    ramp = latest.get("fitness_ramp_rate_7d")
    recovery = build_recovery_summary(sleep, latest["date"])
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "latest_date": latest["date"],
        "fitness": latest["fitness"],
        "fatigue": latest["fatigue"],
        "form": latest["form"],
        "fitness_ramp_rate_7d": ramp,
        "form_status": form_status(latest["form"]),
        "ramp_status": ramp_status(ramp),
        "recovery": recovery,
        "load_last_7_days": last_n_sum(daily, 7),
        "load_last_28_days": last_n_sum(daily, 28),
        "model_meta": meta,
    }


def status_label(value: str) -> str:
    return {
        "fresh": "Fresh",
        "balanced": "Balanced",
        "going_hard": "Going Hard",
        "overloaded": "Overloaded",
        "recovering": "Recovering",
        "steady": "Steady",
        "building": "Building",
        "good": "Good",
        "stable": "Stable",
        "watch": "Watch",
        "low": "Low",
        "unknown": "Unknown",
    }.get(value, value)


def make_svg(daily: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    width, height = 1280, 1040
    bg = "#f8fafc"
    card = "#ffffff"
    text = "#1f2937"
    muted = "#64748b"
    border = "#d7dde7"
    fitness_c = "#2563eb"
    fatigue_c = "#f97316"
    form_c = "#16a34a"

    points = daily[-90:]
    max_y = max(max(row["fitness"], row["fatigue"], abs(row["form"])) for row in points) + 10
    min_y = min(min(row["form"] for row in points), 0) - 10
    plot_x, plot_y, plot_w, plot_h = 86, 720, 1120, 230

    def x_at(i: int) -> float:
        if len(points) == 1:
            return plot_x
        return plot_x + i * plot_w / (len(points) - 1)

    def y_at(value: float) -> float:
        return plot_y + (max_y - value) * plot_h / (max_y - min_y)

    def polyline(key: str, color: str) -> str:
        coords = " ".join(f"{x_at(i):.1f},{y_at(row[key]):.1f}" for i, row in enumerate(points))
        return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'

    form_zero_y = y_at(0)
    ramp = summary.get("fitness_ramp_rate_7d") or 0
    ramp_pos = max(0.0, min(1.0, (ramp + 2) / 10))
    marker_x = 70 + ramp_pos * 1120

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
        f'<text x="54" y="66" font-family="Segoe UI, Arial, sans-serif" font-size="34" font-weight="700" fill="{text}">Performance Management</text>',
        f'<text x="54" y="96" font-family="Segoe UI, Arial, sans-serif" font-size="17" fill="{muted}">Fitness, Form, Fatigue e Ramp Rate calculados pela sua carga diaria estimada.</text>',
    ]

    cards = [
        ("Fitness", summary["fitness"], fitness_c, "carga cronica"),
        ("Form", summary["form"], form_c if summary["form"] >= -10 else fatigue_c, "fitness - fatigue"),
        ("Fatigue", summary["fatigue"], fatigue_c, "carga aguda"),
    ]
    for i, (title, value, color, caption) in enumerate(cards):
        x = 54 + i * 405
        svg += [
            f'<rect x="{x}" y="128" width="360" height="158" rx="18" fill="{card}" stroke="{border}" stroke-width="3"/>',
            f'<text x="{x+36}" y="195" font-family="Segoe UI, Arial, sans-serif" font-size="58" font-weight="700" fill="{color}">{value}</text>',
            f'<line x1="{x+36}" y1="222" x2="{x+318}" y2="222" stroke="{border}" stroke-width="3"/>',
            f'<text x="{x+36}" y="260" font-family="Segoe UI, Arial, sans-serif" font-size="25" fill="{muted}">{title}</text>',
            f'<text x="{x+230}" y="260" font-family="Segoe UI, Arial, sans-serif" font-size="15" fill="{muted}">{caption}</text>',
        ]

    svg += [
        f'<rect x="54" y="312" width="1170" height="310" rx="18" fill="{card}" stroke="{border}" stroke-width="3"/>',
        f'<text x="86" y="362" font-family="Segoe UI, Arial, sans-serif" font-size="24" fill="{muted}">Fitness Ramp Rate</text>',
        f'<text x="86" y="408" font-family="Segoe UI, Arial, sans-serif" font-size="38" font-weight="700" fill="{text}">{status_label(summary["ramp_status"])}</text>',
        f'<text x="835" y="362" font-family="Segoe UI, Arial, sans-serif" font-size="24" fill="{muted}">Recovery</text>',
        f'<text x="835" y="408" font-family="Segoe UI, Arial, sans-serif" font-size="38" font-weight="700" fill="{form_c if summary["recovery"]["status"] in {"good", "stable"} else fatigue_c}">{summary["recovery"].get("score", "--")}</text>',
        f'<text x="925" y="408" font-family="Segoe UI, Arial, sans-serif" font-size="24" fill="{muted}">{status_label(summary["recovery"]["status"])}</text>',
        f'<rect x="86" y="455" width="1120" height="18" rx="9" fill="#e5e7eb"/>',
        f'<rect x="86" y="455" width="280" height="18" rx="9" fill="#cbd5e1"/>',
        f'<rect x="374" y="455" width="270" height="18" fill="#94a3b8"/>',
        f'<rect x="652" y="455" width="270" height="18" fill="#64748b"/>',
        f'<rect x="930" y="455" width="276" height="18" rx="9" fill="#334155"/>',
        f'<path d="M {marker_x:.1f} 442 L {marker_x-16:.1f} 421 L {marker_x+16:.1f} 421 Z" fill="{text}"/>',
        f'<text x="86" y="510" font-family="Segoe UI, Arial, sans-serif" font-size="20" fill="{muted}">Recovering</text>',
        f'<text x="1076" y="510" font-family="Segoe UI, Arial, sans-serif" font-size="20" fill="{muted}">Going Hard</text>',
        f'<text x="86" y="560" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="{muted}">Ramp 7d: {summary["fitness_ramp_rate_7d"]} | Load 7d: {summary["load_last_7_days"]} | Load 28d: {summary["load_last_28_days"]} | Sleep: {summary["recovery"].get("period", "--")}</text>',
    ]

    svg += [
        f'<rect x="54" y="650" width="1170" height="330" rx="18" fill="{card}" stroke="{border}" stroke-width="3"/>',
        f'<text x="86" y="690" font-family="Segoe UI, Arial, sans-serif" font-size="22" fill="{text}" font-weight="700">Ultimos 90 dias</text>',
        f'<line x1="{plot_x}" y1="{form_zero_y:.1f}" x2="{plot_x+plot_w}" y2="{form_zero_y:.1f}" stroke="#cbd5e1" stroke-width="2"/>',
        polyline("fitness", fitness_c),
        polyline("fatigue", fatigue_c),
        polyline("form", form_c),
        f'<text x="905" y="690" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{fitness_c}">Fitness</text>',
        f'<text x="995" y="690" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{fatigue_c}">Fatigue</text>',
        f'<text x="1095" y="690" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{form_c}">Form</text>',
    ]

    svg.append("</svg>")
    return "\n".join(svg)


def write_markdown(summary: dict[str, Any], daily: list[dict[str, Any]]) -> None:
    latest = daily[-1]
    last_activities = []
    for row in daily[-7:]:
        for activity in row["activities"]:
            last_activities.append(
                f"- {row['date']} | {activity['type']} | {activity['name']} | load {activity['estimated_load']}"
            )

    md = [
        "# Performance Management Model",
        "",
        f"Gerado em: {summary['generated_at']}",
        "",
        "## 1. Valores atuais",
        f"- Data final da serie: {summary['latest_date']}",
        f"- Fitness: {summary['fitness']}",
        f"- Fatigue: {summary['fatigue']}",
        f"- Form: {summary['form']} ({status_label(summary['form_status'])})",
        f"- Fitness Ramp Rate 7d: {summary['fitness_ramp_rate_7d']} ({status_label(summary['ramp_status'])})",
        f"- Recovery: {summary['recovery'].get('score')} ({status_label(summary['recovery']['status'])})",
        f"- Carga dos ultimos 7 dias: {summary['load_last_7_days']}",
        f"- Carga dos ultimos 28 dias: {summary['load_last_28_days']}",
        "",
        "## 2. Como o modelo funciona",
        "- Fitness = carga cronica estimada, suavizada em 42 dias.",
        "- Fatigue = carga aguda estimada, suavizada em 7 dias.",
        "- Form = Fitness - Fatigue.",
        "- Ramp Rate = variacao da Fitness nos ultimos 7 dias.",
        "- Recovery = leitura de sono mais recente disponivel, priorizando media semanal quando nao ha diario atualizado.",
        "- A carga diaria usa uma formula tipo TRIMP com FC media quando existe, multiplicador por modalidade e bonus pequeno para D+.",
        "",
        "## 3. Leitura de treinador",
    ]

    if summary["form"] < -25:
        md.append("- O modelo esta lendo fadiga alta. A prioridade imediata e absorver carga.")
    elif summary["form"] < -10:
        md.append("- O modelo esta lendo bloco forte. Isso pode ser produtivo, mas pede cuidado com acumulacao.")
    elif summary["form"] <= 10:
        md.append("- O modelo esta lendo equilibrio: ha carga, mas sem sinal extremo de fadiga no marcador composto.")
    else:
        md.append("- O modelo esta lendo frescor. Bom para prova, mas se durar demais pode indicar carga baixa.")

    if summary["ramp_status"] == "going_hard":
        md.append("- A rampa semanal esta alta; para Arequipa isso so e bom se vier acompanhada de sono e pernas respondendo.")
    elif summary["ramp_status"] == "building":
        md.append("- A rampa semanal esta em construcao: bom sinal para evoluir sem pressa.")
    elif summary["ramp_status"] == "recovering":
        md.append("- A rampa semanal esta em recuperacao: util quando vem depois de prova ou bloco pesado.")
    else:
        md.append("- A rampa semanal esta estavel.")

    recovery = summary["recovery"]
    if recovery["status"] == "watch":
        md.append(f"- Recovery pede atencao: o sono medio em {recovery.get('period')} foi {recovery.get('score')}, com variacao de {recovery.get('score_delta_vs_previous_week')} ponto(s) contra a semana anterior.")
    elif recovery["status"] in {"good", "stable"}:
        md.append(f"- Recovery esta em zona util: sono medio {recovery.get('score')} em {recovery.get('period')}.")
    elif recovery["status"] == "low":
        md.append(f"- Recovery esta baixo: o sono medio em {recovery.get('period')} ficou em {recovery.get('score')}.")

    md += [
        "",
        "## 4. Atividades dos ultimos 7 dias com carga",
        *(last_activities or ["- Nenhuma atividade registrada nos ultimos 7 dias."]),
        "",
        "## 5. Limites",
        "- Este nao e o algoritmo proprietario do TrainingPeaks; e um modelo proprio para o agente do atleta.",
        "- Quando nao ha FC media, o modelo estima intensidade por tipo de atividade.",
        "- Para provas de montanha, a altimetria oficial deve continuar prevalecendo sobre o relogio quando existir.",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    activities = collect_activities()
    sleep = load_json(SLEEP_PATH) if SLEEP_PATH.exists() else None
    daily, meta = build_daily_loads(activities, sleep)
    if not daily:
        raise SystemExit("Sem atividades validas para calcular o modelo.")

    summary = build_summary(daily, meta, sleep)
    payload = {
        "summary": summary,
        "daily_series": daily,
        "model_notes": [
            "Modelo inspirado em CTL/ATL/TSB, mas calculado localmente com carga estimada do atleta.",
            "Fitness usa constante de 42 dias; Fatigue usa constante de 7 dias.",
            "Form negativo indica fadiga acima da base cronica; Form positivo indica mais frescor.",
        ],
    }
    save_json(payload, OUT_JSON)
    write_markdown(summary, daily)
    OUT_SVG.write_text(make_svg(daily, summary), encoding="utf-8")

    if PROFILE_PATH.exists():
        profile = load_json(PROFILE_PATH)
        profile["performance_management_latest"] = summary
        save_json(profile, PROFILE_PATH)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_SVG}")


if __name__ == "__main__":
    main()
