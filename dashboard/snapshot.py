from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from dashboard.repository import dataset_bytes, read_dataset, repository_context, revision_metadata

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/Sao_Paulo")


def load(root: Path, name: str, default: Any = None) -> Any:
    return read_dataset(root, f"data/{name}.json", default)


def fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))


def activity_kind(row: dict) -> str:
    value = fold(str(row.get("type", "")))
    if "run" in value or "corrida" in value:
        return "running"
    if "weight" in value or "strength" in value or "forca" in value or row.get("classification_hint") == "forca":
        return "strength"
    if "swim" in value or "natacao" in value:
        return "swimming"
    if "ride" in value or "cycling" in value or "bicicleta" in value:
        return "cycling"
    return "other"


def seconds(value: Any) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    try:
        result = 0.0
        for part in str(value).split(":"):
            result = result * 60 + float(part)
        return result
    except (ValueError, TypeError):
        return 0.0


LABELS = {
    "prostate": "Próstata", "thyroid": "Tireoide", "glucose_metabolism": "Glicemia",
    "lipid_profile": "Perfil lipídico", "complete_blood_count": "Hemograma", "inflammation": "Inflamação",
    "renal": "Função renal", "liver": "Função hepática", "electrolytes_and_minerals": "Eletrólitos e minerais",
    "vitamins": "Vitaminas", "coagulation": "Coagulação", "urinalysis": "Urina", "results": "Resultados",
    "resting_ecg": "ECG de repouso", "carotid_and_vertebral_doppler": "Doppler",
    "echocardiogram": "Ecocardiograma", "exercise_stress_test": "Teste de esforço", "vitals": "Sinais vitais",
    "psa_total_ng_ml": "PSA total (ng/mL)", "psa_free_ng_ml": "PSA livre (ng/mL)", "free_total_ratio": "Relação livre/total",
    "tsh_miu_l": "TSH (mUI/L)", "free_t4_ng_dl": "T4 livre (ng/dL)", "glucose_mg_dl": "Glicose (mg/dL)",
    "hba1c_pct": "HbA1c (%)", "estimated_average_glucose_mg_dl": "Glicemia média estimada (mg/dL)",
    "total_cholesterol_mg_dl": "Colesterol total (mg/dL)", "hdl_mg_dl": "HDL (mg/dL)", "ldl_mg_dl": "LDL (mg/dL)",
    "vldl_mg_dl": "VLDL (mg/dL)", "non_hdl_mg_dl": "Não HDL (mg/dL)", "triglycerides_mg_dl": "Triglicerídeos (mg/dL)",
    "hemoglobin_g_dl": "Hemoglobina (g/dL)", "hematocrit_pct": "Hematócrito (%)", "leukocytes_mm3": "Leucócitos (/mm³)",
    "platelets_mm3": "Plaquetas (/mm³)", "lymphocytes_absolute_mm3": "Linfócitos absolutos (/mm³)",
    "neutrophils_absolute_mm3": "Neutrófilos absolutos (/mm³)", "high_sensitivity_crp_mg_dl": "PCR ultrassensível (mg/dL)",
    "high_sensitivity_crp_mg_l": "PCR ultrassensível (mg/L)", "creatinine_mg_dl": "Creatinina (mg/dL)", "urea_mg_dl": "Ureia (mg/dL)",
    "egfr_ckd_epi_2021_ml_min_1_73m2": "TFG estimada (mL/min/1,73 m²)", "ast_u_l": "AST / TGO (U/L)",
    "alt_u_l": "ALT / TGP (U/L)", "ggt_u_l": "GGT (U/L)", "zinc_ug_ml": "Zinco (µg/mL)",
    "vitamin_b12_ng_l": "Vitamina B12 (ng/L)", "vitamin_d_25oh_ng_ml": "Vitamina D (ng/mL)",
    "average_24h_mm_hg": "Pressão média 24h (mmHg)", "average_awake_mm_hg": "Pressão em vigília (mmHg)",
    "average_sleep_mm_hg": "Pressão no sono (mmHg)", "heart_rate_bpm": "FC (bpm)",
    "blood_pressure_mm_hg": "Pressão arterial (mmHg)", "oxygen_saturation_pct": "Saturação (%)",
    "left_ventricular_ejection_fraction_pct": "Fração de ejeção (%)", "conclusion": "Conclusão do registro",
    "interpretation": "Interpretação registrada", "flag": "Observação registrada", "flags": "Observações registradas",
    "temperature_c": "Temperatura (°C)", "exam_summary": "Resumo do exame",
}


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def flatten(value: Any, prefix: str = "") -> list[dict]:
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(flatten(child, f"{prefix} / {label(key)}" if prefix else label(key)))
    elif isinstance(value, list):
        if all(not isinstance(x, (dict, list)) for x in value):
            result.append({"label": prefix, "value": "; ".join(map(str, value))})
        else:
            for index, child in enumerate(value):
                result.extend(flatten(child, f"{prefix} {index + 1}"))
    elif value is not None:
        result.append({"label": prefix, "value": "Sim" if value is True else "Não" if value is False else str(value)})
    return result


def medical_documents(root: Path) -> dict[str, Path]:
    history = load(root, "medical_history", {})
    documents = {}
    allowed = (root / "activities" / "notes" / "medical").resolve()
    for record in history.get("records", []):
        for raw in ([record["source_file"]] if record.get("source_file") else record.get("source_files", [])):
            path = (root / str(raw).replace("\\", "/")).resolve()
            if path.is_relative_to(allowed) and path.is_file():
                documents[hashlib.sha256(str(raw).encode()).hexdigest()[:20]] = path
    return documents


def build_snapshot(root: Path = ROOT, today: date | None = None) -> dict:
    with repository_context(root):
        result = _build_snapshot(root, today)
        metadata = revision_metadata()
        if metadata:
            result["storage"] = {key:value for key,value in metadata.items() if key != "warnings"}
            result["sync_warnings"] = metadata["warnings"]
        return result


def _build_snapshot(root: Path = ROOT, today: date | None = None) -> dict:
    today = today or datetime.now(TZ).date()
    history = load(root, "training_history", [])
    hevy = {x["hevy_workout_id"]: x for x in load(root, "hevy_workouts", [])}
    strength = load(root, "strength_training_consolidated", [])
    activities = []
    for index, row in enumerate(history):
        elevation = row.get("official_elevation_gain_m")
        elevation = row.get("watch_elevation_gain_m") if elevation is None else elevation
        activities.append({
            "id": str(row.get("garmin_activity_id") or row.get("activity_key") or f"local-{index}"),
            "date": row.get("date"), "date_time": row.get("date_time"), "name": row.get("hevy_title") or row.get("name"),
            "kind": activity_kind(row), "type": row.get("type"), "distance_km": row.get("distance_km"),
            "duration_seconds": seconds(row.get("duration_seconds") or row.get("elapsed_time")),
            "elapsed_time": row.get("elapsed_time"), "moving_time": row.get("moving_time"),
            "avg_hr": row.get("avg_hr"), "max_hr": row.get("max_hr"), "elevation_gain_m": elevation,
            "elevation_source": "official" if row.get("official_elevation_gain_m") is not None else "watch",
            "pace": row.get("pace_avg"), "source": row.get("source"), "hevy_workout_id": row.get("hevy_workout_id"),
        })
    activities.sort(key=lambda x: (x.get("date") or "", x.get("date_time") or ""), reverse=True)
    strengths = []
    for row in strength:
        workout_ids = row.get("hevy_workout_ids") or ([row["hevy_workout_id"]] if row.get("hevy_workout_id") else [])
        exercises = [exercise for workout_id in workout_ids for exercise in hevy.get(workout_id, {}).get("exercises", [])]
        strengths.append({
            "id": row.get("hevy_workout_id") or row.get("garmin_activity_id") or f"strength-{len(strengths)}",
            "date": row.get("date"), "title": row.get("hevy_title") or "Força / Garmin",
            "classification": row.get("classification"), "match_status": row.get("garmin_match_status"),
            "duration": row.get("garmin_elapsed_time") or row.get("hevy_duration"), "avg_hr": row.get("garmin_avg_hr"),
            "max_hr": row.get("garmin_max_hr"), "garmin_activity_ids": row.get("garmin_activity_ids") or ([row["garmin_activity_id"]] if row.get("garmin_activity_id") else []),
            "sets": row.get("hevy_total_sets"), "working_sets": row.get("hevy_working_sets"),
            "reps": row.get("hevy_total_reps"), "volume_kg": row.get("hevy_total_volume_kg"),
            "exercises": exercises, "exercise_count": row.get("hevy_exercise_count"),
        })
    strengths.sort(key=lambda x: x.get("date") or "", reverse=True)
    model = load(root, "performance_management_model", {})
    series = [{k: row.get(k) for k in ("date", "fitness", "fatigue", "form", "daily_load", "activity_count", "fitness_ramp_rate_7d")}
              for row in model.get("daily_series", [])]
    body = load(root, "body_metrics", {})
    medical = load(root, "medical_history", {})
    documents = medical_documents(root)
    records = []
    for row in medical.get("records", []):
        values = {k: v for k, v in row.items() if k not in ("date", "label", "type", "source_file", "source_files", "historical_trends_from_report")}
        links = []
        for raw in ([row["source_file"]] if row.get("source_file") else row.get("source_files", [])):
            key = hashlib.sha256(str(raw).encode()).hexdigest()[:20]
            if key in documents:
                links.append({"id": key, "name": documents[key].name})
        records.append({"date": row.get("date"), "label": row.get("label"), "type": row.get("type"),
                        "values": values, "rows": flatten(values), "documents": links,
                        "trends": row.get("historical_trends_from_report", {})})
    profile = load(root, "athlete_profile", {})
    goals = load(root, "season_goals", {})
    summary = model.get("summary", {})
    start = (today - timedelta(days=6)).isoformat()
    recent = [x for x in activities if start <= (x.get("date") or "") <= today.isoformat()]
    recent_strength = [x for x in strengths if start <= (x.get("date") or "") <= today.isoformat()]
    freshness = {"activities": max((x.get("date") or "" for x in activities), default=None),
                 "strength": max((x.get("date") or "" for x in strengths), default=None),
                 "body": body.get("reference_date"), "medical": medical.get("updated_at"),
                 "model": summary.get("generated_at"), "sleep_score": summary.get("recovery", {}).get("last_scored_date")}
    insights = ["Fitness, fadiga e forma são índices do modelo local de carga, não medidas clínicas nem o algoritmo do TrainingPeaks.",
                "O volume de força usa os registros do Hevy; sessões vinculadas ao Garmin não são contadas duas vezes.",
                "A carga usa a base Garmin/Strava. Sessões disponíveis somente no Hevy aparecem no diário de força, mas não são automaticamente adicionadas à série de carga."]
    if summary.get("recovery", {}).get("status") == "unknown":
        insights.append("Recuperação sem pontuação atual de sono. Forma positiva não comprova recuperação fisiológica.")
    if body.get("reference_date"):
        insights.append(f"Composição corporal é a avaliação de {body['reference_date']}; não é uma estimativa do corpo de hoje.")
    digest = hashlib.sha256()
    for name in ("training_history", "hevy_workouts", "strength_training_consolidated", "body_metrics", "medical_history", "performance_management_model"):
        raw = dataset_bytes(root, f"data/{name}.json")
        if raw is not None:
            digest.update(raw)
    race_index = read_dataset(root, "analysis/races/last_10_race_performance_index.json", {})
    return {"schema_version": 1, "model_version": "athlete-load-42-7/v1", "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "as_of": today.isoformat(), "source_digest": digest.hexdigest(), "freshness": freshness,
            "athlete": {"name": profile.get("name") or "Atleta", "age": profile.get("age"), "current_goal": profile.get("current_goal"),
                        "endurance_goal": profile.get("current_endurance_goal")},
            "goals": {"health": goals.get("current_health_goal"), "endurance": goals.get("current_primary_goal")},
            "performance": {"summary": summary, "series": series, "notes": model.get("model_notes", [])},
            "activities": activities, "strength": strengths, "race_index": race_index,
            "week": {"start": start, "end": today.isoformat(), "activity_count": len(recent),
                     "running_km": round(sum(x.get("distance_km") or 0 for x in recent if x["kind"] == "running"), 2),
                     "running_elevation_m": round(sum(x.get("elevation_gain_m") or 0 for x in recent if x["kind"] == "running")),
                     "strength_sessions": len(recent_strength), "working_sets": sum(x.get("working_sets") or 0 for x in recent_strength),
                     "strength_volume_kg": round(sum(x.get("volume_kg") or 0 for x in recent_strength)),
                     "minutes": round(sum(x["duration_seconds"] for x in recent) / 60), "by_kind": dict(Counter(x["kind"] for x in recent))},
            "body": {**{k: body.get(k) for k in ("reference_date", "active_goal", "perimetry_current_cm", "skinfolds_current_mm")},
                     "current": body.get("current") or {}, "history": body.get("history") or []},
            "nutrition": load(root, "nutrition_targets", {}),
            "medical": {"updated_at": medical.get("updated_at"), "status": medical.get("current_status", {}),
                        "context": medical.get("pre_analytical_context", {}), "records": records,
                        "disclaimer": "Exibição de dados e interpretações já registrados na base. Não substitui consulta nem emite diagnóstico."},
            "physiology": [{k: v for k, v in x.items() if k not in ("source_file", "patient_name_raw", "date_of_birth_raw")} for x in load(root, "physiology_tests", [])],
            "insights": insights}
