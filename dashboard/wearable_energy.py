"""Wearable daily-energy coverage inference, recent reference and calibration.

The watch total is a device estimate, never a measurement of metabolism, and
sources remain alternatives rather than additive components. Coverage is only
upgraded by explicit provider evidence or by a verifiable observation
timestamp; absence of a flag is not proof of a complete day.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta


def _known(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _local_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError, TypeError:
        return None


def _local_datetime(value) -> datetime | None:
    """Parse a timestamp ignoring its offset; provider fields are already local."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError, TypeError:
        return None


def infer_coverage(
    date: str, observed_at: str | None, wellness_start_local: str | None = None
) -> tuple[str, float | None]:
    if not observed_at:
        return "unknown", None
    day_date = _local_date(date)
    observed = _local_datetime(observed_at)
    if day_date is None or observed is None:
        return "unknown", None
    observed_day = observed.date()
    if observed_day > day_date:
        return "complete", 24.0
    if observed_day < day_date:
        return "unknown", None
    day_start = datetime.combine(day_date, datetime.min.time())
    start = _local_datetime(wellness_start_local) if wellness_start_local else None
    if start is None or start < day_start:
        start = day_start
    hours = round(max((observed - start).total_seconds() / 3600, 0), 1)
    return "partial", hours


def with_inferred_coverage(row: dict) -> dict:
    """Backfill coverage from the observation timestamp; never overrides an explicit value."""
    if row.get("coverage") in (None, "unknown") and row.get("observed_at"):
        coverage, hours = infer_coverage(
            row.get("date") or "", row["observed_at"], row.get("wellness_start_local") or row.get("interval_start")
        )
        if coverage == "unknown":
            return row
        return {
            **row,
            "coverage": coverage,
            "coverage_hours": hours,
            "coverage_basis": "inferred_from_observation_time",
        }
    return row


def _complete(row) -> bool:
    return row.get("coverage") in ("full", "complete") and (
        row.get("coverage_hours") is None or row["coverage_hours"] >= 24
    )


def recent_reference(rows: list[dict], day: date, *, window_days: int = 14, min_days: int = 7) -> dict | None:
    """Mean of full-coverage wearable days in [day - window_days, day - 1]; the day itself is excluded."""
    day = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    start, end = day - timedelta(days=window_days), day - timedelta(days=1)
    by_day = {}
    for raw in rows:
        row = with_inferred_coverage(raw) if isinstance(raw, dict) else raw
        if not isinstance(row, dict) or not _known(row.get("total_kcal")) or not _complete(row):
            continue
        row_day = _local_date(row.get("date"))
        if row_day is None or not start <= row_day <= end:
            continue
        by_day[row_day] = row
    if len(by_day) < min_days:
        return None
    ordered = [by_day[d] for d in sorted(by_day)]
    totals = [row["total_kcal"] for row in ordered]
    resting = [row["resting_kcal"] for row in ordered if _known(row.get("resting_kcal"))]
    return {
        "total_kcal": round(statistics.mean(totals)),
        "resting_kcal": round(statistics.mean(resting)) if resting else None,
        "median_kcal": round(statistics.median(totals)),
        "min_kcal": round(min(totals)),
        "max_kcal": round(max(totals)),
        "days_used": len(totals),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "source": "garmin_recent_mean",
        "method": "wearable_recent_mean_14d_v1",
        "assumptions": [
            f"Referência pela média de {len(totals)} dias completos do relógio entre "
            f"{start.strftime('%d/%m')} e {end.strftime('%d/%m')}; estimativa do dispositivo, não medição do metabolismo.",
            "A média já inclui treinos e rotina observada; calorias de atividades não são somadas novamente.",
        ],
    }


def calibrate(
    reference_kcal: float,
    series: list[dict],
    weights: list[dict],
    *,
    min_usable_days: int = 10,
    min_weight_points: int = 4,
    min_weight_span_days: int = 14,
    max_shift_pct: float = 0.15,
) -> dict:
    """Adjust a reference expenditure by intake and the least-squares weight trend.

    The conversion of 7700 kcal per kg of body mass is a product hypothesis,
    not a measurement of tissue composition; the correction is clamped to
    ±max_shift_pct of the reference so the trend nudges rather than replaces it.
    """
    usable_days = [row for row in series if row.get("usable")]
    weight_points = [w for w in weights if _known(w.get("weight_kg")) and _local_date(w.get("date"))]
    first = _local_date(weight_points[0]["date"]) if weight_points else None
    last = _local_date(weight_points[-1]["date"]) if weight_points else None
    span = (last - first).days if first and last else 0
    observed = {
        "usable_days": len(usable_days),
        "weight_points": len(weight_points),
        "weight_span_days": span,
    }
    missing = []
    if len(usable_days) < min_usable_days:
        missing.append(f"{min_usable_days} dias completos de ingestão e gasto (há {len(usable_days)})")
    if len(weight_points) < min_weight_points:
        missing.append(f"{min_weight_points} medidas de peso (há {len(weight_points)})")
    if span < min_weight_span_days:
        missing.append(f"medidas de peso abrangendo ao menos {min_weight_span_days} dias (há {span})")
    if missing:
        return {
            "status": "insufficient",
            **observed,
            "required": {
                "usable_days": min_usable_days,
                "weight_points": min_weight_points,
                "weight_span_days": min_weight_span_days,
            },
            "missing": missing,
        }
    from dashboard.health import _weight_slope_kg_per_week

    weekly = _weight_slope_kg_per_week(weight_points) or 0.0
    slope_per_day = weekly / 7
    intake = statistics.mean(row["intake_kcal"] for row in usable_days)
    implied = intake - slope_per_day * 7700
    raw_shift = implied - reference_kcal
    limit = max_shift_pct * reference_kcal
    shift = max(-limit, min(limit, raw_shift))
    return {
        "status": "applied",
        "implied_tdee_kcal": round(implied),
        "calibrated_kcal": round(reference_kcal + shift),
        "shift_kcal": round(shift),
        "clamped": abs(raw_shift) > limit,
        **observed,
        "weekly_change_kg": round(weekly, 3),
        "method": "intake_weight_trend_calibration_v1",
    }
