"""User-reviewed health memory and transparent, versioned energy/goal calculations.

No provider calls or LLM calls occur here. SQLite supports isolated installations
and tests; the existing operational database adapter uses PostgreSQL in production.
All writes, including plan decisions, publish an immutable state revision.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dashboard.repository import operational_db, postgres_enabled, read_dataset

MODEL_VERSION = "personal_energy_mifflin_v1"
POLICY_VERSION = "conservative_trend_v1"
POLICY = {
    "review_days": 14, "review_frequency_days": 7,
    "min_complete_days": 10, "min_weight_measurements": 4,
    "adjustment_kcal": 100, "initial_deficit_kcal": 250,
    "max_planned_deficit_pct": 0.15, "min_target_kcal": 1200,
    "trend_tolerance_kg_week": 0.15, "adherence_tolerance_pct": 0.15,
    "desired_weekly_change_kg": -0.25, "sleep_target_hours": 7,
}
KINDS = {"measurements", "checkins", "goals", "energy_records", "plans"}
GOAL_TYPES = {"fat_loss", "maintenance", "strength", "endurance", "sleep", "consistency", "custom", "weight_gain"}
GOAL_STATUSES = {"active", "paused", "completed", "archived"}


class ConflictError(ValueError):
    """The client's state or the evidence behind a proposal has changed."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _reference_date(value):
    """Accept dated legacy references without converting missing dates into observations."""
    if not value:
        return None
    try:
        return _day(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _legacy_goal(value, category, today):
    if isinstance(value, str):
        description, raw = value.strip(), {}
    elif isinstance(value, dict):
        raw = value
        description = next((raw[key].strip() for key in ("description", "goal", "name", "objective", "title", "notes")
                            if isinstance(raw.get(key), str) and raw[key].strip()), "")
    else:
        return None
    if not description or len(description) > 1000:
        return None
    statuses = {"active": "active", "current": "active", "ativo": "active", "paused": "paused", "pausado": "paused",
                "completed": "completed", "done": "completed", "finished": "completed", "concluido": "completed", "concluído": "completed",
                "archived": "archived", "arquivado": "archived"}
    status = statuses.get(str(raw.get("status", "active")).lower(), "active")
    if raw.get("completed") is True or raw.get("is_completed") is True:
        status = "completed"
    effective = next((parsed for key in ("effective_from", "start_date", "date", "baseline_date", "updated_at")
                      if (parsed := _reference_date(raw.get(key)))), today.isoformat())
    kind = raw.get("type") if raw.get("type") in GOAL_TYPES else "endurance" if category == "endurance" else "custom"
    result = {"id": "legacy-" + category + "-" + _fingerprint({"description": description, "effective_from": effective})[:24],
              "description": description, "type": kind, "status": status, "priority": 1 if category == "health" else 2,
              "source": "legacy_reference", "effective_from": effective, "record_version": 1}
    for key in ("target_kcal", "target_value", "baseline_value", "desired_weekly_change_kg"):
        if key not in raw or not isinstance(raw[key], (int, float)) or isinstance(raw[key], bool) or not math.isfinite(raw[key]):
            continue
        try:
            if key == "target_kcal":
                _number(raw[key], key, 500, 10000)
            elif key == "desired_weekly_change_kg":
                _number(raw[key], key, -0.5, 0.5)
            else:
                _number(raw[key], key, -10000, 10000)
            result[key] = raw[key]
        except ValueError:
            pass
    for key in ("due_date", "baseline_date"):
        if parsed := _reference_date(raw.get(key)):
            result[key] = parsed
    if isinstance(raw.get("target_metric"), str) and len(raw["target_metric"]) <= 80:
        result["target_metric"] = raw["target_metric"]
    if isinstance(raw.get("preserve"), list) and all(isinstance(x, str) and len(x) < 200 for x in raw["preserve"]):
        result["preserve"] = raw["preserve"][:20]
    if isinstance(raw.get("notes"), str) and len(raw["notes"]) <= 5000:
        result["notes"] = raw["notes"]
    return result


def _stamp():
    return datetime.now(UTC).isoformat()


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError) as error:
        raise ValueError("Informe uma data válida no formato AAAA-MM-DD.") from error


def _today(preferences=None):
    return datetime.now(ZoneInfo((preferences or {}).get("timezone", "America/Sao_Paulo"))).date()


def _number(value, label, low=0, high=10000, nullable=True):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label}: informe um número entre {low} e {high}.")
    return float(value)


def _known(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _text(value, label, maximum=5000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{label}: texto inválido.")
    return value.strip()


def _validate_object(value):
    if not isinstance(value, dict):
        raise ValueError("O registro deve ser um objeto.")
    try:
        raw = _json(value)
    except (TypeError, ValueError) as error:
        raise ValueError("O registro contém valores inválidos.") from error
    if len(raw) > 60000:
        raise ValueError("O registro excede o tamanho permitido.")
    return copy.deepcopy(value)


def _policy(preferences):
    return {**POLICY, **{key: value for key, value in preferences.items() if key in POLICY}}


def _validate_section(section, value):
    row = _validate_object(value)
    if section == "profile":
        for key, low, high in (("height_cm", 50, 260), ("weight_kg", 20, 500), ("age", 18, 120), ("manual_tdee_kcal", 500, 10000)):
            if key in row:
                _number(row[key], key, low, high)
        if row.get("birth_date"):
            birth = _day(row["birth_date"])
            if birth > _today():
                raise ValueError("A data de nascimento não pode estar no futuro.")
        if row.get("sex") not in (None, "", "male", "female", "other", "unspecified"):
            raise ValueError("Parâmetro de sexo inválido para o modelo de energia.")
        if "name" in row:
            row["name"] = _text(row["name"], "Nome", 200)
    elif section == "preferences":
        if 'auto_nutrition_targets' in row and not isinstance(row['auto_nutrition_targets'], bool):
            raise ValueError('A atualização automática das metas deve ser verdadeiro ou falso.')
        if row.get("energy_method", "auto") not in {"auto", "model", "wearable"}:
            raise ValueError("Método de gasto deve ser auto, model ou wearable.")
        limits: dict[str, tuple[float, float]] = {"activity_factor": (1, 2.5), "review_days": (7, 90), "review_frequency_days": (1, 90),
                  "min_complete_days": (1, 90), "min_weight_measurements": (4, 90),
                  "adjustment_kcal": (25, 200), "initial_deficit_kcal": (0, 500),
                  "max_planned_deficit_pct": (0, 0.2), "min_target_kcal": (1000, 4000),
                  "trend_tolerance_kg_week": (0.05, 0.5), "adherence_tolerance_pct": (0.05, 0.3),
                  "desired_weekly_change_kg": (-0.5, 0.5), "sleep_target_hours": (5, 12), "ai_daily_limit": (0, 100)}
        for field, (minimum, maximum) in limits.items():
            if field in row:
                _number(row[field], field, minimum, maximum, nullable=False)
        policy = _policy(row)
        if policy["min_complete_days"] > policy["review_days"] or policy["min_weight_measurements"] > policy["review_days"]:
            raise ValueError("A cobertura mínima não pode exceder a janela de revisão.")
    else:
        raise ValueError("Seção de perfil desconhecida.")
    if row.get("timezone"):
        try:
            ZoneInfo(row["timezone"])
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError("Fuso horário inválido.") from error
    if row.get("effective_from"):
        row["effective_from"] = _day(row["effective_from"]).isoformat()
    return row


def _validate_record(kind, value):
    if kind not in KINDS:
        raise ValueError("Tipo de registro desconhecido.")
    row = _validate_object(value)
    if row.get("id"):
        row["id"] = _text(row["id"], "Identificador", 150)
        if not row["id"]:
            raise ValueError("Identificador vazio.")
    if kind in {"measurements", "checkins", "energy_records"}:
        row["date"] = _day(row.get("date")).isoformat()
    if kind == "measurements":
        bounds = {"weight_kg": (20, 500), "body_fat_pct": (1, 75), "lean_mass_kg": (10, 300), "waist_cm": (20, 300)}
        if not any(row.get(key) is not None for key in bounds):
            raise ValueError("Registre ao menos uma medida corporal.")
        for key, (low, high) in bounds.items():
            if key in row:
                _number(row[key], key, low, high)
    elif kind == "checkins":
        for key in ("fatigue", "hunger", "mood", "pain", "stress"):
            if key in row:
                _number(row[key], key, 0, 10)
        if "sleep_hours" in row:
            _number(row["sleep_hours"], "Sono em horas", 0, 24)
        if "illness" in row and not isinstance(row["illness"], bool):
            raise ValueError("Doença relatada deve ser verdadeiro ou falso.")
    elif kind == "energy_records":
        for key in ("total_kcal", "active_kcal", "exercise_kcal", "resting_kcal"):
            if key in row:
                _number(row[key], key, 0, 20000)
        if row.get("total_kcal") is None:
            raise ValueError("Informe o gasto total diário; componentes isolados não são um total.")
        if "coverage_hours" in row:
            _number(row["coverage_hours"], "Horas observadas", 0, 24)
        if row.get("coverage", "unknown") not in {"full", "complete", "partial", "unknown"}:
            raise ValueError("Cobertura de gasto inválida.")
        if "is_projection" in row and not isinstance(row["is_projection"], bool):
            raise ValueError("Projeção deve ser verdadeiro ou falso.")
        row.setdefault("source", "manual")
        row.setdefault("method", "declared_daily_total_v1")
        row.setdefault("coverage", "unknown")
    elif kind == "goals":
        row.setdefault("type", "custom")
        if row["type"] not in GOAL_TYPES:
            raise ValueError("Tipo de objetivo inválido.")
        row.setdefault("status", "active")
        if row["status"] not in GOAL_STATUSES:
            raise ValueError("Estado do objetivo inválido.")
        row.setdefault("priority", 1)
        _number(row["priority"], "Prioridade", 1, 20, nullable=False)
        row["description"] = _text(row.get("description", ""), "Objetivo", 1000)
        if not row["description"]:
            raise ValueError("Descreva o objetivo.")
        for key in ("due_date", "baseline_date", "effective_from"):
            if row.get(key):
                row[key] = _day(row[key]).isoformat()
        if row.get("target_kcal") is not None:
            _number(row["target_kcal"], "Meta de ingestão", 500, 10000)
        if row.get("target_value") is not None:
            _number(row["target_value"], "Valor desejado", -10000, 10000)
        if row.get("desired_weekly_change_kg") is not None:
            _number(row["desired_weekly_change_kg"], "Variação semanal desejada", -0.5, 0.5)
        if "preserve" in row and (not isinstance(row["preserve"], list) or any(not isinstance(i, str) for i in row["preserve"])):
            raise ValueError("Aspectos a preservar devem ser uma lista de textos.")
    elif kind == "plans":
        if not isinstance(row.get("goal_id"), str):
            raise ValueError("Associe o plano a um objetivo.")
        if row.get("target_kcal") is not None:
            _number(row["target_kcal"], "Meta de ingestão", 500, 10000)
        for key in ('protein_g', 'carbs_g', 'fat_g'):
            if row.get(key) is not None:
                _number(row[key], key, 0, 2500)
        for key in ("effective_from", "next_review_date"):
            if row.get(key):
                row[key] = _day(row[key]).isoformat()
    for key in ("notes", "reason"):
        if key in row:
            row[key] = _text(row[key], key)
    return row


def _empty():
    return {"revision": 0, "profile": {}, "preferences": {}, "profile_versions": [], "preference_versions": [],
            **{kind: [] for kind in KINDS}, "goal_versions": [], "proposals": [], "decisions": [], "history": []}


def _legacy_profile(snapshot):
    meta = snapshot.get("meta", {})
    athlete = meta.get("athlete", snapshot.get("athlete", {})) or {}
    return {key: value for key, value in {"name": athlete.get("name"), "age": athlete.get("age"),
                                        "height_cm": athlete.get("height_cm"), "sex": athlete.get('sex')}.items() if value is not None}


def _effective_values(state, section, day):
    versions = state.get("profile_versions" if section == "profile" else "preference_versions", [])
    eligible = [row for row in versions if row["effective_from"] <= day.isoformat()]
    if eligible:
        return copy.deepcopy(eligible[-1]["value"])
    # An undated empty section is harmless; a future explicit version is not historical context.
    return copy.deepcopy(state[section]) if not versions else {}


def _weights(state, snapshot, end):
    records = [row for row in state["measurements"] if row.get("weight_kg") is not None and row["date"] <= end.isoformat()]
    for row in snapshot.get("body", {}).get("history", []):
        recorded = row.get("date") or row.get("measured_on")
        if recorded and _known(row.get("weight_kg")) and str(recorded)[:10] <= end.isoformat():
            records.append({**row, "date": str(recorded)[:10], "source": row.get("source", "legacy_reference")})
    # Explicit personal measurements win over a legacy duplicate for the same date.
    by_day = {}
    for row in sorted(records, key=lambda r: (r["date"], r.get("source") != "legacy_reference", r.get("updated_at", ""))):
        by_day[row["date"]] = row
    return [by_day[key] for key in sorted(by_day)]


def _profile_for_day(state, snapshot, day):
    profile = {**_legacy_profile(snapshot), **_effective_values(state, "profile", day)}
    weights = _weights(state, snapshot, day)
    if weights:
        profile["weight_kg"] = weights[-1]["weight_kg"]
        profile["weight_reference_date"] = weights[-1]["date"]
    return profile


def _model(profile, preferences, day):
    if _known(profile.get("manual_tdee_kcal")):
        return {"total_kcal": profile["manual_tdee_kcal"], "resting_kcal": None,
                "method": "declared_profile_daily_total_v1", "source": "profile_declared", "assumptions": []}
    age = profile.get("age")
    if profile.get("birth_date"):
        birth = _day(profile["birth_date"])
        age = day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))
    needed = {"weight_kg": profile.get("weight_kg"), "height_cm": profile.get("height_cm"),
              "age": age, "sex": profile.get("sex"), "activity_factor": preferences.get("activity_factor")}
    if any(needed[k] is None for k in needed) or needed["sex"] not in {"male", "female"}:
        return None
    if not all(_known(needed[k]) for k in ("weight_kg", "height_cm", "age", "activity_factor")) or not 18 <= age <= 120:
        return None
    resting = 10 * needed["weight_kg"] + 6.25 * needed["height_cm"] - 5 * age + (5 if needed["sex"] == "male" else -161)
    return {"total_kcal": round(resting * needed["activity_factor"], 1), "resting_kcal": round(resting, 1),
            "method": MODEL_VERSION, "source": "profile_model", "assumptions": [
                "Estimativa Mifflin-St Jeor para adulto; fator de atividade declarado inclui exercício habitual.",
                "Não representa medição do metabolismo nem acrescenta calorias isoladas de treinos."]}


def _goals_for_day(state, day):
    """Select the reviewed goal version effective at that date, including removals."""
    versions = state.get("goal_versions", [])
    dated = {}
    versioned_ids = {row["goal_id"] for row in versions}
    for row in versions:
        if row["effective_from"] <= day.isoformat():
            dated[row["goal_id"]] = row["value"]
    for goal in state["goals"]:
        if goal["id"] not in versioned_ids and goal.get("effective_from", "0001-01-01") <= day.isoformat():
            dated[goal["id"]] = goal
    return [copy.deepcopy(value) for value in dated.values() if value is not None]


def _primary_goal(state, day):
    candidates = [g for g in _goals_for_day(state, day) if g.get("status", "active") == "active"]
    return min(candidates, key=lambda g: (g.get("priority", 1), g.get("created_at", ""))) if candidates else None


def _active_plan(state, day, goal=None):
    goal = goal or _primary_goal(state, day)
    if not goal:
        return None
    candidates = [p for p in state["plans"] if p.get("goal_id") == goal["id"] and p.get("status") in {"active", "provisional", "superseded"}
                  and p.get("effective_from", "0001-01-01") <= day.isoformat()
                  and (not p.get("valid_to") or p["valid_to"] >= day.isoformat())]
    return max(candidates, key=lambda p: (p.get("effective_from", ""), p.get("version", 1), p.get("created_at", ""))) if candidates else None


def _initial_plan(state, goal, day):
    prefs = state["preferences"]
    policy = _policy(prefs)
    profile = _profile_for_day(state, {}, day)
    model = _model(profile, prefs, day)
    existing = [p for p in state["plans"] if p.get("goal_id") == goal["id"]]
    target = goal.get("target_kcal")
    method = "declared_target_v1" if target is not None else "tracking_plan_v1"
    limitations = []
    if target is None and model and goal["type"] in {"fat_loss", "maintenance"}:
        change = min(policy["initial_deficit_kcal"], model["total_kcal"] * policy["max_planned_deficit_pct"])
        target = model["total_kcal"] - change if goal["type"] == "fat_loss" else model["total_kcal"]
        target = max(policy["min_target_kcal"], model.get("resting_kcal") or 0, target)
        method = MODEL_VERSION + ":initial_target"
        limitations = model["assumptions"] + ["Referência operacional estimada; revisar com dados de ingestão, corpo e recuperação."]
    if target is None:
        limitations.append("Plano de acompanhamento sem alvo calórico. Informe um alvo ou perfil suficiente para a estimativa quando necessário.")
    return {"id": uuid.uuid4().hex, "goal_id": goal["id"], "version": max([p.get("version", 1) for p in existing] + [0]) + 1,
            "status": "active" if target is not None else "provisional", "target_kcal": round(target, 1) if target is not None else None,
            "baseline_expenditure_kcal": model["total_kcal"] if model else None, "method": method,
            "effective_from": day.isoformat(), "next_review_date": (day + timedelta(days=int(policy["review_frequency_days"]))).isoformat(),
            "source": "user_declared" if goal.get("target_kcal") is not None else "deterministic_calculation",
            "reason": "Plano inicial associado ao objetivo e à disponibilidade de dados.", "limitations": limitations,
            "tracking": ["Registrar alimentação e cobertura", "Registrar medidas datadas", "Acompanhar treino, sono e percepção"], "created_at": _stamp()}


def _publish_plan(state, plan):
    for prior in state["plans"]:
        if (prior.get("goal_id") == plan["goal_id"] and prior.get("status") in {"active", "provisional"}
                and prior.get('effective_from', '0001-01-01') <= plan['effective_from']):
            prior["status"] = "superseded"
            prior["valid_to"] = (_day(plan["effective_from"]) - timedelta(days=1)).isoformat()
    future = [p['effective_from'] for p in state['plans'] if p.get('goal_id') == plan['goal_id']
              and p.get('status') in {'active', 'provisional', 'superseded'}
              and p.get('effective_from', '') > plan['effective_from']
              and (not p.get('valid_to') or p['valid_to'] >= p['effective_from'])]
    if future:
        plan['valid_to'] = (_day(min(future)) - timedelta(days=1)).isoformat()
    state["plans"].append(plan)


def _food(record):
    entries = record.get("entries", [])
    values, pending = [], 0
    for entry in entries:
        items = (entry.get("analysis") or {}).get("items", [])
        if not items:
            pending += 1
        for item in items:
            if _known(item.get("kcal")):
                values.append(item["kcal"])
            else:
                pending += 1
    pending = max(pending, record.get("pending_count", 0) or 0)
    status = record.get("completeness", record.get("coverage", record.get("status")))
    complete = status in {"complete", "declared_complete", "full"} or record.get("complete") is True
    fasting = record.get("fasting_declared") is True
    # Empty complete days only represent zero intake when fasting was explicitly declared.
    usable = complete and pending == 0 and bool(entries or fasting)
    if record.get("complete_nutrition") is False:
        usable = False
    return {"record": record, "registered_kcal": round(sum(values), 1), "intake_kcal": round(sum(values), 1) if usable else None,
            "intake_status": "complete" if complete else "partial" if entries else "empty",
            "calorie_status": "pending" if pending else "complete" if entries or fasting else "unknown", "pending_count": pending}


def _provider_energy(snapshot, root):
    rows = snapshot.get("energy_records", snapshot.get("daily_energy"))
    if rows is None:
        rows = read_dataset(root, "data/daily_energy.json", [])
    if isinstance(rows, dict):
        rows = rows.get("daily", [])
    return rows if isinstance(rows, list) else []


def _energy(state, snapshot, day, food, provider_rows):
    profile = _profile_for_day(state, snapshot, day)
    preferences = _effective_values(state, "preferences", day)
    manual = [r for r in state["energy_records"] if r["date"] == day.isoformat()]
    providers = [r for r in provider_rows if str(r.get("date", ""))[:10] == day.isoformat() and _known(r.get("total_kcal"))]
    # Sources are alternatives, never additive. Unknown wearable coverage remains
    # unknown even when a separately identified full-day model is selected.
    manual = sorted(manual, key=lambda r: r.get("updated_at", ""), reverse=True)
    candidates = manual + providers
    complete = lambda row: row.get("coverage") in {"full", "complete"} and (row.get("coverage_hours") is None or row["coverage_hours"] >= 24)
    method_choice = preferences.get("energy_method", "auto")
    possible_model = _model(profile, preferences, day)
    source, model = None, None
    if method_choice == "wearable":
        source = next((r for r in providers if complete(r)), providers[0] if providers else None)
    elif method_choice == "model":
        model = possible_model
    else:
        source = next((r for r in manual if complete(r)), None) or next((r for r in providers if complete(r)), None)
        if source is None:
            model = possible_model
            if model is None:
                source = candidates[0] if candidates else None
    total = source.get("total_kcal") if source else model["total_kcal"] if model else None
    coverage = source.get("coverage", "unknown") if source else "full" if model else "unknown"
    if coverage == "complete":
        coverage = "full"
    hours = source.get("coverage_hours") if source else 24 if model else None
    if hours is not None and hours < 24:
        coverage = "partial"
    projection = bool(source.get("is_projection", False)) if source else bool(model and day >= _today(preferences))
    expenditure_usable = total is not None and coverage == "full" and not projection
    usable = expenditure_usable and food["intake_kcal"] is not None
    plan = _active_plan(state, day)
    target = plan.get("target_kcal") if plan else None
    limitations = list(model.get("assumptions", [])) if model else []
    if model and candidates:
        limitations.append("Usado modelo integral do perfil. As fontes do relógio/manuais não foram completadas nem somadas; permanecem alternativas com sua cobertura original.")
    if method_choice == "model" and model is None:
        limitations.append("O método de perfil foi escolhido, mas faltam dados suficientes para calcular o gasto.")
    if method_choice == "wearable" and source is None:
        limitations.append("O método do relógio foi escolhido, mas não há gasto diário dessa fonte para a data.")
    if coverage != "full":
        limitations.append("O gasto tem cobertura parcial ou desconhecida; não permite déficit retrospectivo do dia completo.")
    if projection:
        limitations.append("Gasto projetado, distinto de um gasto retrospectivo para o dia encerrado.")
    if food["intake_kcal"] is None:
        limitations.append("O diário alimentar não é utilizável como ingestão total: revise a cobertura e estimativas pendentes.")
    return {"date": day.isoformat(), **{k: food[k] for k in ("registered_kcal", "intake_kcal", "intake_status", "calorie_status", "pending_count")},
            "expenditure_kcal": round(total, 1) if total is not None else None,
            "expenditure_status": "projected" if projection else "available" if expenditure_usable else "partial" if total is not None else "unknown",
            "source": source.get("source", "unknown") if source else model["source"] if model else None,
            "method": source.get("method", "daily_total_v1") if source else model["method"] if model else None,
            "model_version": MODEL_VERSION, "coverage": coverage, "coverage_hours": hours, "is_projection": projection,
            "energy_method": method_choice, "coverage_basis": "modeled_full_day" if model else "source_declared_full" if coverage == "full" else "source_partial_or_unknown",
            "modeled_hours": 24 if model else None, "observed_hours": source.get("coverage_hours") if source else None,
            "deficit_kcal": round(total - food["intake_kcal"], 1) if usable else None,
            "balance_kcal": round(food["intake_kcal"] - total, 1) if usable else None,
            "planned_intake_kcal": target, "margin_kcal": round(target - food["registered_kcal"], 1) if target is not None else None,
            "usable": usable, "expenditure_usable": expenditure_usable,
            "components": {key: source.get(key) if source else model.get(key) if model else None
                           for key in ("total_kcal", "active_kcal", "exercise_kcal", "resting_kcal")},
            "observed_at": source.get("observed_at") if source else None, "limitations": limitations,
            "alternatives": [{"source": r.get("source"), "total_kcal": r.get("total_kcal"), "coverage": r.get("coverage", "unknown"),
                              "coverage_hours": r.get("coverage_hours"), "method": r.get("method"), "is_projection": r.get("is_projection", False)}
                             for r in candidates if r is not source]}


def _progress(state, snapshot, day, days):
    start = day - timedelta(days=days - 1)
    weights = [r for r in _weights(state, snapshot, day) if r["date"] >= start.isoformat()]
    weekly = None
    if len(weights) >= 2:
        origin = _day(weights[0]["date"])
        xs = [(_day(w["date"]) - origin).days for w in weights]
        ys = [w["weight_kg"] for w in weights]
        mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator:
            weekly = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator * 7
    goal_progress = []
    for goal in _goals_for_day(state, day):
        metric = goal.get("target_metric")
        relevant = [m for m in state["measurements"] if m["date"] <= day.isoformat() and _known(m.get(metric))] if metric else []
        latest = max(relevant, key=lambda m: m["date"]) if relevant else None
        baseline, target = goal.get("baseline_value"), goal.get("target_value")
        current = latest.get(metric) if latest else None
        pct = (current - baseline) / (target - baseline) * 100 if all(_known(v) for v in (current, baseline, target)) and target != baseline else None
        goal_progress.append({"goal_id": goal["id"], "metric": metric, "current_value": current, "reference_date": latest["date"] if latest else None,
                              "baseline_value": baseline, "target_value": target, "progress_pct": round(pct, 1) if pct is not None else None})
    return {"weight_measurements": len(weights), "weight_dates": [w["date"] for w in weights],
            "first_weight_kg": weights[0]["weight_kg"] if weights else None,
            "last_weight_kg": weights[-1]["weight_kg"] if weights else None,
            "weight_change_kg": round(weights[-1]["weight_kg"] - weights[0]["weight_kg"], 3) if len(weights) >= 2 else None,
            "weekly_change_kg": round(weekly, 3) if weekly is not None else None,
            "trend_method": "least_squares_weight_kg_per_week_v1", "goals": goal_progress}


class HealthStore:
    def __init__(self, runtime: Path, root: Path):
        self.runtime, self.root = Path(runtime), Path(root)
        self.runtime.mkdir(parents=True, exist_ok=True)
        with operational_db(self.runtime, "health", self.root) as conn:
            if not postgres_enabled(self.root):
                conn.execute("CREATE TABLE IF NOT EXISTS personal_health_state(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL)")
                conn.execute("CREATE TABLE IF NOT EXISTS personal_health_revisions(revision INTEGER PRIMARY KEY,payload TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL)")
            conn.execute("BEGIN IMMEDIATE")
            raw, stamp = _json(_empty()), _stamp()
            conn.execute("INSERT OR IGNORE INTO personal_health_state(id,revision,payload,updated_at) VALUES(?,?,?,?)", ("state", 0, raw, stamp))
            conn.execute("INSERT OR IGNORE INTO personal_health_revisions(revision,payload,reason,created_at) VALUES(?,?,?,?)", (0, raw, "initial", stamp))

    def read(self, revision=None):
        with operational_db(self.runtime, "health", self.root) as conn:
            row = conn.execute("SELECT payload FROM personal_health_state WHERE id=?", ("state",)).fetchone() if revision is None else conn.execute(
                "SELECT payload FROM personal_health_revisions WHERE revision=?", (revision,)).fetchone()
            if row is None:
                raise ValueError("Versão de saúde não encontrada.")
            return json.loads(row[0])

    def seed_legacy(self, snapshot):
        """Adopt current legacy references once, without overwriting user-owned memory.

        Only the two current goal references are considered; completed expeditions
        and arbitrary historical season lists are never promoted to active goals.
        Body observations retain their original date, and numerical targets must
        be explicit. An empty installation remains revision zero.
        """
        existing = self.read()
        if existing["revision"] != 0 or existing.get("legacy_imported"):
            return existing
        raw_profile = read_dataset(self.root, "data/athlete_profile.json", {})
        raw_preferences = read_dataset(self.root, "data/athlete_preferences.json", {})
        raw_profile = raw_profile if isinstance(raw_profile, dict) else {}
        raw_preferences = raw_preferences if isinstance(raw_preferences, dict) else {}
        today = _today()
        athlete = snapshot.get("athlete", {}) or {}
        profile = {}
        for key in ("name", "age", "height_cm", "birth_date", "sex", "weight_kg"):
            value = raw_profile.get(key, athlete.get(key))
            if value is None:
                continue
            try:
                field = _validate_section("profile", {key: value})
                profile[key] = field[key]
            except ValueError:
                pass
        # Import only actual dated body observations. Profile weight alone is not
        # silently converted into a new measurement dated today.
        body = snapshot.get("body", {}) or {}
        observations = []
        for row in body.get("history", []) or []:
            if not isinstance(row, dict):
                continue
            recorded = _reference_date(row.get("date") or row.get("measured_on"))
            if recorded and recorded <= today.isoformat():
                observations.append({"date": recorded, **{key: row.get(key) for key in ("weight_kg", "body_fat_pct", "lean_mass_kg", "waist_cm") if row.get(key) is not None}})
        recorded = _reference_date(body.get("reference_date"))
        if recorded and recorded <= today.isoformat() and isinstance(body.get("current"), dict):
            observations.append({"date": recorded, **{key: body["current"].get(key) for key in ("weight_kg", "body_fat_pct", "lean_mass_kg", "waist_cm") if body["current"].get(key) is not None}})
        measurements = []
        for candidate in sorted(observations, key=lambda row: row["date"], reverse=True):
            valid = {"date": candidate["date"]}
            for key, value in candidate.items():
                if key == "date":
                    continue
                try:
                    _validate_record("measurements", {"date": candidate["date"], key: value})
                    valid[key] = value
                except ValueError:
                    pass
            if len(valid) > 1:
                measurements.append({**valid, "id": "legacy-body-" + _fingerprint(valid)[:24], "source": "legacy_reference", "record_version": 1})
                break
        if measurements and measurements[0].get("weight_kg") is not None:
            profile["weight_kg"] = measurements[0]["weight_kg"]
            profile["weight_reference_date"] = measurements[0]["date"]
        preferences = {}
        allowed_preferences = set(POLICY) | {"activity_factor", "energy_method", "timezone", "units", "modalities", "sports", "availability",
            "equipment", "dietary_preferences", "avoided_foods", "allergies", "restrictions", "priorities", "notes"}
        for key in allowed_preferences:
            if key not in raw_preferences:
                continue
            try:
                _validate_section("preferences", {key: raw_preferences[key]})
                preferences[key] = raw_preferences[key]
            except ValueError:
                pass
        try:
            _validate_section("preferences", preferences)
        except ValueError:
            # Keep defaults when legacy policy values conflict with one another.
            preferences = {k: v for k, v in preferences.items() if k not in POLICY}
        goals = []
        current_goals = snapshot.get("goals", {})
        if isinstance(current_goals, dict):
            for category in ("health", "endurance"):
                goal = _legacy_goal(current_goals.get(category), category, today)
                if goal:
                    goals.append(goal)
        if not any((profile, preferences, measurements, goals)):
            return existing
        reference = next((parsed for key in ("reference_date", "updated_at", "generated_at")
                          if (parsed := _reference_date(raw_profile.get(key)))), measurements[0]["date"] if measurements else today.isoformat())
        preference_reference = next((parsed for key in ("effective_from", "updated_at", "generated_at")
                                     if (parsed := _reference_date(raw_preferences.get(key)))), reference)
        def seed(state):
            if state["revision"] != 0 or state.get("legacy_imported"):
                return
            if profile:
                state["profile"] = {**profile, "source": "legacy_reference", "effective_from": reference}
                state["profile_versions"].append({"version": 1, "effective_from": reference, "value": copy.deepcopy(state["profile"])})
            if preferences:
                state["preferences"] = {**preferences, "source": "legacy_reference", "effective_from": preference_reference}
                state["preference_versions"].append({"version": 1, "effective_from": preference_reference, "value": copy.deepcopy(state["preferences"])})
            for measurement in measurements:
                measurement.update(created_at=_stamp(), updated_at=_stamp())
                state["measurements"].append(measurement)
            for goal in goals:
                goal.update(created_at=_stamp(), updated_at=_stamp())
                state["goals"].append(goal)
                state.setdefault("goal_versions", []).append({"goal_id": goal["id"], "version": 1,
                    "effective_from": goal["effective_from"], "value": copy.deepcopy(goal)})
                if goal["status"] == "active":
                    plan = _initial_plan(state, goal, _day(goal["effective_from"]))
                    if goal.get("target_kcal") is None:
                        plan.update(target_kcal=None, status="provisional", method="legacy_reference_tracking_v1",
                                    reason="Referência atual importada; confirme um alvo antes de aplicar uma meta numérica.")
                    plan["source"] = "legacy_reference"
                    state["plans"].append(plan)
            state["legacy_imported"] = {"version": 1, "at": _stamp(), "source": "legacy_reference"}
        # The guard is checked inside the same write transaction as the marker.
        return self._change("seed:legacy_reference", seed)

    def _change(self, reason, operation, expected_revision=None):
        with operational_db(self.runtime, "health", self.root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT revision,payload FROM personal_health_state WHERE id=?", ("state",)).fetchone()
            if expected_revision is not None and row[0] != expected_revision:
                raise ConflictError("Os dados foram alterados. Atualize a página antes de salvar.")
            state = json.loads(row[1])
            before = _json(state)
            operation(state)
            if _json(state) == before:
                return state
            state["revision"] = row[0] + 1
            state["history"].append({"revision": state["revision"], "reason": reason, "created_at": _stamp()})
            raw = _json(state)
            conn.execute("INSERT INTO personal_health_revisions(revision,payload,reason,created_at) VALUES(?,?,?,?)", (state["revision"], raw, reason, _stamp()))
            conn.execute("UPDATE personal_health_state SET revision=?,payload=?,updated_at=? WHERE id=?", (state["revision"], raw, _stamp(), "state"))
            return state

    def update(self, section, value, expected_revision=None):
        value = _validate_section(section, value)
        def update(state):
            merged = {**state[section], **value}
            _validate_section(section, merged)
            if merged == state[section]:
                return
            state[section] = merged
            versions = "profile_versions" if section == "profile" else "preference_versions"
            effective = value.get("effective_from", _today(state["preferences"]).isoformat())
            state[versions].append({"version": len(state[versions]) + 1, "effective_from": effective, "value": copy.deepcopy(merged)})
            # Fill a provisional plan once profile inputs become available; keep confirmed numerical plans.
            for goal in state["goals"]:
                if goal.get("status") == "active":
                    current = _active_plan(state, _today(state["preferences"]), goal)
                    if current and current.get("target_kcal") is None:
                        candidate = _initial_plan(state, goal, _today(state["preferences"]))
                        if candidate["target_kcal"] is not None:
                            _publish_plan(state, candidate)
        return self._change("update:" + section, update, expected_revision)

    def save(self, kind, record, expected_revision=None):
        value = _validate_record(kind, record)
        record_id = value.get("id") or uuid.uuid4().hex
        def save(state):
            old = next((r for r in state[kind] if r["id"] == record_id), None)
            value["id"] = record_id
            if old and all(old.get(k) == v for k, v in value.items()):
                return
            merged = {**(old or {}), **value}
            _validate_record(kind, merged)
            merged.update(record_version=(old or {}).get("record_version", 0) + 1, created_at=(old or {}).get("created_at", _stamp()), updated_at=_stamp())
            goal_effective = None
            if kind == "goals":
                # The objective's original start date differs from the validity of a later edit.
                goal_effective = value.get("version_effective_from")
                if goal_effective is None:
                    goal_effective = value.get("effective_from") if not old or value.get("effective_from") != old.get("effective_from") else None
                goal_effective = _day(goal_effective or _today(state["preferences"]).isoformat()).isoformat()
                merged.setdefault("effective_from", goal_effective)
                versions = state.setdefault("goal_versions", [])
                versions.append({"goal_id": record_id, "version": merged["record_version"], "effective_from": goal_effective, "value": copy.deepcopy(merged)})
            if kind == "plans":
                if not any(g["id"] == merged["goal_id"] for g in state["goals"]):
                    raise ValueError("O objetivo desse plano não existe.")
                merged.setdefault("version", max([p.get("version", 1) for p in state["plans"] if p.get("goal_id") == merged["goal_id"]] + [0]) + 1)
                merged.setdefault("status", "active" if merged.get("target_kcal") is not None else "provisional")
                merged.setdefault("effective_from", _today(state["preferences"]).isoformat())
                merged.setdefault("method", "declared_plan_v1")
                merged.setdefault("next_review_date", (_day(merged["effective_from"]) + timedelta(days=int(_policy(state["preferences"])["review_frequency_days"]))).isoformat())
                if old:
                    raise ValueError("Planos são imutáveis: salve uma nova versão ou retorne a uma versão anterior.")
                _publish_plan(state, merged)
            else:
                state[kind] = [r for r in state[kind] if r["id"] != record_id] + [merged]
            if kind == "goals" and merged["status"] == "active":
                effective = _day(goal_effective)
                current = _active_plan(state, effective, merged)
                changed = not old or any(old.get(k) != merged.get(k) for k in ("target_kcal", "type", "preserve", "desired_weekly_change_kg"))
                if not current or changed:
                    _publish_plan(state, _initial_plan(state, merged, effective))
        return self._change("save:" + kind + ":" + record_id, save, expected_revision)

    def remove(self, kind, record_id, expected_revision=None):
        if kind not in KINDS:
            raise ValueError("Tipo de registro desconhecido.")
        def remove(state):
            if kind == "goals" and any(row["id"] == record_id for row in state[kind]):
                state.setdefault("goal_versions", []).append({"goal_id": record_id, "version": len(state.get("goal_versions", [])) + 1,
                    "effective_from": _today(state["preferences"]).isoformat(), "value": None})
            state[kind] = [r for r in state[kind] if r["id"] != record_id]
        return self._change("remove:" + kind + ":" + str(record_id), remove, expected_revision)

    def _summary(self, state, day, snapshot, diary, days):
        day = _day(day)
        days = int(days)
        if not 1 <= days <= 90:
            raise ValueError("O período deve conter de 1 a 90 dias.")
        provider_rows = _provider_energy(snapshot, self.root)
        selected_days = [day - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
        records = diary.read_many(selected_days)
        foods, series = [], []
        for selected in selected_days:
            food = _food(records[selected])
            foods.append(food["record"])
            series.append(_energy(state, snapshot, selected, food, provider_rows))
        usable = [r for r in series if r["usable"]]
        policy = _policy(_effective_values(state, "preferences", day))
        summary = {"revision": state["revision"], "date": day.isoformat(), "profile": _profile_for_day(state, snapshot, day),
                   "preferences": _effective_values(state, "preferences", day), "goals": _goals_for_day(state, day), "plans": state["plans"],
                   "active_goal": _primary_goal(state, day), "active_plan": _active_plan(state, day), "energy": series[-1], "series": series,
                   "coverage": {"days": days, "food_complete_days": sum(r["intake_kcal"] is not None for r in series),
                                "energy_usable_days": sum(r["expenditure_usable"] for r in series), "balance_usable_days": len(usable),
                                "sum_deficit_kcal": round(sum(r["deficit_kcal"] for r in usable), 1) if usable else None,
                                "avg_deficit_kcal": round(statistics.mean(r["deficit_kcal"] for r in usable), 1) if usable else None},
                   "progress": _progress(state, snapshot, day, days), "proposals": state["proposals"], "decisions": state["decisions"],
                   "policy": {**policy, "version": POLICY_VERSION}, "history": state["history"]}
        return summary, foods

    def summary(self, day, snapshot, diary, days=14):
        return self._summary(self.read(), day, snapshot, diary, days)[0]

    def _evidence(self, state, day, snapshot, diary):
        day = _day(day)
        prefs = _effective_values(state, "preferences", day)
        policy = _policy(prefs)
        summary, foods = self._summary(state, day, snapshot, diary, int(policy["review_days"]))
        start = (day - timedelta(days=int(policy["review_days"]) - 1)).isoformat()
        checkins = [r for r in state["checkins"] if start <= r["date"] <= day.isoformat()]
        sleep = snapshot.get("sleep", {})
        sleep_rows = sleep.get("daily", []) if isinstance(sleep, dict) else []
        sleep_rows = [r for r in sleep_rows if start <= str(r.get("date", ""))[:10] <= day.isoformat()]
        loads = [r for r in snapshot.get("performance", {}).get("series", []) if start <= str(r.get("date", ""))[:10] <= day.isoformat()]
        active_goals = [g for g in _goals_for_day(state, day) if g.get("status") == "active"]
        evidence = {"date": day.isoformat(), "policy": summary["policy"], "profile": summary["profile"], "preferences": prefs,
                    "goal": summary["active_goal"], "plan": summary["active_plan"], "active_goals": active_goals,
                    "energy": summary["series"], "food": foods, "progress": summary["progress"], "checkins": checkins, "sleep": sleep_rows, "load": loads}
        # Proposals, decisions, global revision and generated history do not invalidate their own evidence.
        return summary, evidence, _fingerprint(evidence)

    def review(self, day, snapshot, diary):
        day = _day(day)
        state = self.read()
        summary, evidence, fingerprint = self._evidence(state, day, snapshot, diary)
        same = next((p for p in state["proposals"] if p.get("fingerprint") == fingerprint and p.get("status") == "pending"), None)
        if same:
            return {"proposal": same, "state": state}
        goal, plan, policy = summary["active_goal"], summary["active_plan"], summary["policy"]
        coverage, progress = summary["coverage"], summary["progress"]
        action, delta = "maintain", 0
        limitations = ["A tendência do peso não mede isoladamente gordura ou massa magra; o gasto e a ingestão continuam estimativas."]
        reason = "Manter o acompanhamento e reavaliar no próximo período."
        enough = coverage["food_complete_days"] >= policy["min_complete_days"] and progress["weight_measurements"] >= policy["min_weight_measurements"]
        span = (_day(progress["weight_dates"][-1]) - _day(progress["weight_dates"][0])).days if progress["weight_dates"] else 0
        enough = enough and span >= 7 and progress["weekly_change_kg"] is not None
        if not goal or not plan or plan.get("target_kcal") is None:
            action, reason = "collect_data", "Defina um objetivo e um plano numérico quando pertinente; registre dados úteis antes de adaptar a ingestão."
        elif not enough:
            action, reason = "collect_data", f"Dados insuficientes: são necessários {policy['min_complete_days']} dias completos com calorias e {policy['min_weight_measurements']} medidas em datas distintas, abrangendo ao menos sete dias."
        elif goal["type"] not in {"fat_loss", "maintenance", "weight_gain"}:
            reason = "O objetivo principal é comportamental ou esportivo; não há justificativa para alterar a ingestão pela tendência de peso."
        elif goal["type"] == "weight_gain" and goal.get("desired_weekly_change_kg") is None:
            action, reason = "collect_data", "Informe a variação desejada para esse objetivo de ganho antes de propor um ajuste numérico; não pressupor manutenção ou uma taxa de ganho."
        else:
            intake = statistics.mean(r["intake_kcal"] for r in summary["series"] if r["intake_kcal"] is not None)
            target = plan["target_kcal"]
            adherence = abs(intake - target) / target
            desired = goal.get("desired_weekly_change_kg", policy["desired_weekly_change_kg"] if goal["type"] == "fat_loss" else 0)
            trend = progress["weekly_change_kg"]
            if adherence > policy["adherence_tolerance_pct"]:
                reason = "A ingestão registrada difere do plano além da tolerância; revisar a viabilidade e os registros antes de modificar a meta."
            elif trend > desired + policy["trend_tolerance_kg_week"]:
                delta = -policy["adjustment_kcal"]
                reason = "A tendência está acima da variação desejada, com cobertura e adesão suficientes; propor um ajuste pequeno e reavaliável."
            elif trend < desired - policy["trend_tolerance_kg_week"]:
                delta = policy["adjustment_kcal"]
                reason = "A tendência está abaixo da variação desejada; propor mais energia para moderar a mudança e preservar recuperação."
            else:
                reason = "A tendência está dentro da tolerância da meta; manter o plano e observar o próximo período."
            recent = [r for r in evidence["checkins"] if r["date"] >= (day - timedelta(days=6)).isoformat()]
            sleep_hours = [r.get("duration_minutes", 0) / 60 for r in evidence["sleep"] if _known(r.get("duration_minutes"))]
            sleep_hours += [r["sleep_hours"] for r in recent if _known(r.get("sleep_hours"))]
            risk = any(r.get("illness") or (r.get("pain") or 0) >= 7 for r in recent) or sum((r.get("fatigue") or 0) >= 7 for r in recent) >= 2
            risk = risk or (len(sleep_hours) >= 3 and statistics.mean(sleep_hours) < policy["sleep_target_hours"] - 1)
            competitor = any(g["type"] == "endurance" and g.get("priority", 1) <= goal.get("priority", 1) for g in evidence["active_goals"])
            load_values = [r["daily_load"] for r in evidence["load"] if _known(r.get("daily_load"))]
            if len(load_values) >= 10:
                first, last = statistics.mean(load_values[:7]), statistics.mean(load_values[-7:])
                risk = risk or (first > 0 and last > first * 1.3)
            if delta < 0 and (risk or competitor):
                delta = 0
                reason = "Manter a ingestão: recuperação relatada, aumento de carga ou objetivo esportivo prioritário tornam inadequado propor restrição adicional agora."
            if delta:
                model = _model(summary["profile"], summary["preferences"], day)
                floor = max(policy["min_target_kcal"], (model or {}).get("resting_kcal") or 0)
                baseline = plan.get("baseline_expenditure_kcal") or (model or {}).get("total_kcal")
                if baseline:
                    floor = max(floor, baseline * (1 - policy["max_planned_deficit_pct"]))
                if target + delta < floor:
                    delta = 0
                    reason = "Manter a meta: o ajuste ultrapassaria o limite conservador configurado para o plano."
                else:
                    action = "adjust"
        suggested = copy.deepcopy(plan) if plan else None
        effective = (day + timedelta(days=1)).isoformat()
        if suggested:
            suggested.update(id=uuid.uuid4().hex, version=plan.get("version", 1) + 1, target_kcal=round(plan["target_kcal"] + delta, 1) if plan.get("target_kcal") is not None else None,
                             effective_from=effective, next_review_date=(day + timedelta(days=1 + int(policy["review_frequency_days"]))).isoformat(),
                             reason=reason, method=POLICY_VERSION, source="reviewed_adaptation", created_at=_stamp())
            suggested.pop("valid_to", None)
            suggested["status"] = "active" if suggested.get("target_kcal") is not None else "provisional"
        proposal = {"id": uuid.uuid4().hex, "status": "pending", "review_date": day.isoformat(), "action": action,
                    "reason": reason, "previous_plan": plan, "suggested_plan": suggested, "delta_kcal": delta,
                    "evidence": {"coverage": coverage, "progress": progress, "policy": policy,
                                 "previous_decisions": [d for d in state["decisions"] if d.get("date", "") <= day.isoformat()][-3:]},
                    "limitations": limitations, "effective_from": effective,
                    "next_review_date": (day + timedelta(days=int(policy["review_frequency_days"]))).isoformat(),
                    "fingerprint": fingerprint, "created_at": _stamp()}
        def publish(current):
            for prior in current["proposals"]:
                if prior.get("status") == "pending" and prior.get("review_date") == day.isoformat() and prior.get("fingerprint") != fingerprint:
                    prior["status"] = "stale"
            current["proposals"].append(proposal)
        result = self._change("review:" + day.isoformat(), publish, state["revision"])
        return {"proposal": proposal, "state": result}

    def decide(self, proposal_id, decision, day, snapshot, diary):
        decision = {"accept": "accepted", "reject": "rejected"}.get(decision, decision)
        if decision not in {"accepted", "rejected"}:
            raise ValueError("Escolha aceitar ou rejeitar a proposta.")
        state = self.read()
        proposal = next((p for p in state["proposals"] if p["id"] == proposal_id), None)
        if not proposal:
            raise ValueError("Proposta não encontrada.")
        if proposal["status"] != "pending":
            prior = next((d for d in state["decisions"] if d["proposal_id"] == proposal_id and d["decision"] == decision), None)
            if prior:
                return {"proposal": proposal, "decision": prior, "state": state}
            raise ConflictError("Essa proposta já foi decidida ou está desatualizada. Faça uma nova revisão.")
        review_day = _day(proposal["review_date"])
        _, original_evidence, fingerprint = self._evidence(state, review_day, snapshot, diary)
        decision_day = max(_day(day), _today(state["preferences"]))
        stale = fingerprint != proposal["fingerprint"]
        # A historical review is not permission to change today's different goal or plan.
        if decision == "accepted":
            current_context = (_primary_goal(state, decision_day), _active_plan(state, decision_day),
                               _profile_for_day(state, snapshot, decision_day), _effective_values(state, "preferences", decision_day))
            reviewed_context = (original_evidence["goal"], original_evidence["plan"],
                                original_evidence["profile"], original_evidence["preferences"])
            stale = stale or _json(current_context) != _json(reviewed_context)
        result_decision = {"id": uuid.uuid4().hex, "proposal_id": proposal_id, "decision": decision,
                           "date": decision_day.isoformat(), "created_at": _stamp(), "fingerprint": fingerprint,
                           "previous_plan_id": (proposal.get("previous_plan") or {}).get("id"), "new_plan_id": None}
        def apply(current):
            selected = next(p for p in current["proposals"] if p["id"] == proposal_id)
            if stale:
                selected["status"] = "stale"
                selected["stale_reason"] = "Objetivo, plano ou evidências foram alterados. Gere uma revisão atualizada antes de aceitar."
                return
            selected["status"] = decision
            selected["decided_at"] = _stamp()
            if decision == "accepted" and proposal.get("suggested_plan") and proposal["action"] in {"adjust", "maintain"}:
                plan = copy.deepcopy(proposal["suggested_plan"])
                # A late decision takes effect after its actual date, never rewrites past targets.
                effective = max(_day(plan["effective_from"]), decision_day + timedelta(days=1))
                plan["effective_from"] = effective.isoformat()
                plan["next_review_date"] = (effective + timedelta(days=int(_policy(current["preferences"])["review_frequency_days"]))).isoformat()
                plan["proposal_id"] = proposal_id
                _publish_plan(current, plan)
                result_decision["new_plan_id"] = plan["id"]
            result_decision["state_revision"] = current["revision"] + 1
            current["decisions"].append(result_decision)
        result = self._change("decision:" + proposal_id, apply, state["revision"])
        saved = next(p for p in result["proposals"] if p["id"] == proposal_id)
        if stale:
            raise ConflictError(saved["stale_reason"])
        return {"proposal": saved, "decision": result_decision, "state": result}
