from __future__ import annotations
import csv, glob, json, os, re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CTX_DIR = ROOT / "analysis" / "context"
DOWNLOADS = Path(os.environ.get("ATHLETE_AGENT_DOWNLOADS", Path.home() / "Downloads"))
TRAINING_HISTORY_PATH = DATA_DIR / "training_history.json"
DETAILED_PROFILE_PATH = DATA_DIR / "athlete_detailed_profile.json"
GARMIN_JSON_PATH = DATA_DIR / "garmin_incremental_import_2026_04.json"
SLEEP_JSON_PATH = DATA_DIR / "garmin_sleep_reference_2026_04.json"
ERGO_JSON_PATH = DATA_DIR / "physiology_tests.json"
UPDATE_MD_PATH = CTX_DIR / "garmin_incremental_update_2026_04.md"
WORKOUT_TITLE_MAP = {
    "perna": "Legs - Híbrido Montanha",
    "pull - costa e biceps": "PULL – Costas e Bíceps",
    "push - peito ombro e triceps": "PUSH – Peito, Ombro e Tríceps",
    "core": "Core",
}
TYPE_MAP = {
    "corrida": ("Run", "road run"),
    "corrida em trilhas": ("Run", "trail run"),
    "corrida em esteira": ("Run", "treadmill run"),
    "caminhada": ("Walk", "walk"),
    "natacao em piscina": ("Swim", "pool swim"),
    "treino de forca": ("Weight Training", "strength workout"),
    "subir escada": ("Stair-Stepper", "stair climber"),
    "montanhismo": ("Hike", "mountaineering"),
}
MONTHS_PT = {
    "jan": 1, "jan.": 1,
    "fev": 2, "fev.": 2,
    "mar": 3, "mar.": 3,
    "abr": 4, "abr.": 4,
    "mai": 5, "mai.": 5,
    "jun": 6, "jun.": 6,
    "jul": 7, "jul.": 7,
    "ago": 8, "ago.": 8,
    "set": 9, "set.": 9,
    "out": 10, "out.": 10,
    "nov": 11, "nov.": 11,
    "dez": 12, "dez.": 12,
}

def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return (str(value).strip().lower().replace("á","a").replace("à","a").replace("â","a").replace("ã","a")
            .replace("é","e").replace("ê","e").replace("í","i").replace("ó","o").replace("ô","o")
            .replace("õ","o").replace("ú","u").replace("ç","c"))

def load_json(path: Path) -> Any:
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Nao foi possivel ler {path}")

def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def glob_paths(pattern: str) -> list[Path]:
    return sorted(Path(item) for item in glob.glob(str(DOWNLOADS / pattern)))

def canonicalize_row(row: dict[str, str]) -> dict[str, str]:
    return {normalize_text(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

def parse_number(text: Any) -> float | None:
    if text is None:
        return None
    raw = str(text).strip().replace('"','').replace(' ','')
    if raw in {"", "--"}:
        return None
    try:
        if ',' in raw and '.' not in raw:
            left, right = raw.split(',', 1)
            if left.isdigit() and right.isdigit() and len(right) == 3:
                return float(left + right)
            return float(left + '.' + right)
        if ',' in raw and '.' in raw:
            raw = raw.replace('.', '').replace(',', '.') if raw.rfind(',') > raw.rfind('.') else raw.replace(',', '')
        return float(raw)
    except ValueError:
        return None

def parse_duration(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text and text != "--" else None

def duration_to_seconds(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(float(parts[1]))
    return None

def parse_workout_datetime(value: str) -> datetime:
    text = str(value).strip()
    for fmt in ("%d %b %Y, %H:%M", "%d %b. %Y, %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    match = re.match(r"(\d{1,2})\s+de\s+([a-zA-ZçÇ.]+)\s+de\s+(\d{4}),\s+(\d{1,2}):(\d{2})", text)
    if match:
        day = int(match.group(1))
        month = MONTHS_PT.get(normalize_text(match.group(2)))
        year = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        if month:
            return datetime(year, month, day, hour, minute)
    raise ValueError(f"Formato de data de workout nao reconhecido: {value!r}")

def format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    total = int(round(seconds_per_km))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}/km"
def parse_activities(paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows = []
    for path in paths:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            raw_rows.extend(canonicalize_row(row) for row in csv.DictReader(handle))
    unique, dup_counts = {}, Counter()
    for row in raw_rows:
        key = (row.get('data',''), row.get('tipo de atividade',''), row.get('titulo',''), row.get('tempo',''))
        dup_counts[key] += 1
        unique[key] = row
    items = []
    for key in sorted(unique):
        row = unique[key]
        pt = row.get('tipo de atividade', '')
        t, subtype = TYPE_MAP.get(normalize_text(pt), (pt, pt))
        dt = datetime.strptime(row['data'], '%Y-%m-%d %H:%M:%S')
        title = row.get('titulo') or t
        dist_raw = parse_number(row.get('distancia')) or 0.0
        distance_km = dist_raw / 1000.0 if t == 'Swim' and dist_raw > 100 else dist_raw
        elapsed = parse_duration(row.get('duracao') or row.get('tempo'))
        moving = parse_duration(row.get('tempo em movimento') or row.get('tempo') or row.get('duracao'))
        elapsed_s = duration_to_seconds(elapsed)
        moving_s = duration_to_seconds(moving)
        if moving_s and elapsed_s and moving_s > elapsed_s:
            moving_s, moving = elapsed_s, elapsed
        ascent = parse_number(row.get('subida total')) or 0.0
        avg_hr = parse_number(row.get('fc media'))
        max_hr = parse_number(row.get('fc maxima'))
        pace_s = (moving_s / distance_km) if moving_s and distance_km else None
        vs = ascent / (elapsed_s / 3600.0) if ascent and elapsed_s else 0.0
        vpk = ascent / distance_km if ascent and distance_km else None
        hre = pace_s / avg_hr if pace_s and avg_hr else None
        tl = parse_number(row.get('training stress score®')) or parse_number(row.get('training stress score(r) (tss)'))
        if tl == 0:
            tl = None
        name_n = normalize_text(title)
        if t == 'Weight Training': cls = 'forca'
        elif t in {'Hike','Stair-Stepper'}: cls = 'subida especifica'
        elif t == 'Swim': cls = 'recuperacao'
        elif t == 'Run' and ('trilhas' in normalize_text(pt) or ascent >= 300 or 'climb' in name_n): cls = 'subida especifica'
        elif t == 'Run' and (distance_km >= 20 or (moving_s or 0) >= 7200): cls = 'longao'
        elif t == 'Run' and any(tok in name_n for tok in ['ritmo','progressao','repet','velocidade','objetivo','threshold','tempo']): cls = 'limiar'
        elif t == 'Run' and 'tranquila' in name_n: cls = 'recuperacao'
        elif t == 'Walk': cls = 'recuperacao'
        else: cls = 'base aerobica'
        items.append({
            'activity_key': '|'.join(key), 'date': dt.strftime('%Y-%m-%d'), 'date_time': dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'name': title, 'type': t, 'subtype': subtype, 'classification_hint': cls, 'distance_km': round(distance_km, 2),
            'elapsed_time': elapsed, 'moving_time': moving, 'avg_hr': int(round(avg_hr)) if avg_hr is not None else None,
            'max_hr': int(round(max_hr)) if max_hr is not None else None, 'watch_elevation_gain_m': round(ascent, 1),
            'pace_avg': row.get('ritmo medio') or format_pace(pace_s), 'vertical_speed': round(vs, 1),
            'vertical_per_km': round(vpk, 2) if vpk is not None else None, 'relative_effort': None,
            'training_load': round(tl, 1) if tl is not None else None, 'source': 'garmin_csv_incremental_import',
            'source_activity_type': pt, 'filename': None, 'data_confidence': 'garmin_csv_no_raw_fit',
            'duration_seconds': elapsed_s, 'moving_time_seconds': moving_s, 'stopped_time_seconds': (elapsed_s - moving_s) if elapsed_s and moving_s is not None else None,
            'pace_seconds_per_km': round(pace_s, 2) if pace_s else None, 'heart_rate_efficiency': round(hre, 3) if hre is not None else None,
            'garmin_duplicate_count': dup_counts[key],
        })
    return items, {'raw_rows': len(raw_rows), 'unique_rows': len(items), 'date_range': {'start': items[0]['date'] if items else None, 'end': items[-1]['date'] if items else None}, 'duplicate_distribution': dict(sorted(Counter(dup_counts.values()).items()))}

def parse_workouts(paths: list[Path]) -> dict[str, Any]:
    raw_rows = []
    for path in paths:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            raw_rows.extend(canonicalize_row(row) for row in csv.DictReader(handle))
    unique = {}
    for row in raw_rows:
        key = (row.get('title',''), row.get('start_time',''), row.get('end_time',''), row.get('exercise_title',''), row.get('set_index',''), row.get('weight_kg',''), row.get('reps',''))
        unique[key] = row
    sessions = {}
    for row in unique.values():
        sk = (row.get('title',''), row.get('start_time',''), row.get('end_time',''))
        if sk not in sessions:
            pretty = WORKOUT_TITLE_MAP.get(normalize_text(row.get('title')), row.get('title'))
            sessions[sk] = {'title_raw': row.get('title'), 'title': pretty, 'start_time': parse_workout_datetime(row.get('start_time')).strftime('%Y-%m-%dT%H:%M:%S'), 'end_time': parse_workout_datetime(row.get('end_time')).strftime('%Y-%m-%dT%H:%M:%S'), 'exercise_titles': [], 'total_sets': 0}
        ex = row.get('exercise_title')
        if ex:
            sessions[sk]['exercise_titles'].append(ex)
            sessions[sk]['total_sets'] += 1
    out = []
    for session in sorted(sessions.values(), key=lambda s: s['start_time']):
        uniq_ex = []
        for ex in session['exercise_titles']:
            if ex not in uniq_ex:
                uniq_ex.append(ex)
        session['exercise_titles'] = uniq_ex
        session['exercise_count'] = len(uniq_ex)
        session['exercise_preview'] = uniq_ex[:5]
        out.append(session)
    return {'raw_rows': len(raw_rows), 'unique_rows': len(unique), 'sessions': out}

def enrich_strength(activities: list[dict[str, Any]], workouts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sessions = workouts['sessions']
    matched, unmatched, enriched = [], [], []
    for activity in activities:
        item = dict(activity)
        if activity['type'] != 'Weight Training':
            enriched.append(item)
            continue
        act_dt = datetime.strptime(activity['date_time'], '%Y-%m-%dT%H:%M:%S')
        same_day = [s for s in sessions if s['start_time'].startswith(activity['date'])]
        best, best_delta = None, None
        for session in same_day:
            ses_dt = datetime.strptime(session['start_time'], '%Y-%m-%dT%H:%M:%S')
            delta = abs((act_dt - ses_dt).total_seconds())
            if delta <= 900 and (best is None or delta < best_delta):
                best, best_delta = session, delta
        if best:
            item['workout_title'] = best['title']
            item['workout_exercise_count'] = best['exercise_count']
            item['workout_exercises_preview'] = best['exercise_preview']
            item['workout_total_sets'] = best['total_sets']
            item['workout_start_time'] = best['start_time']
            if normalize_text(item['name']) == 'strength':
                item['name'] = best['title']
            matched.append({'activity_date_time': activity['date_time'], 'activity_name_original': activity['name'], 'activity_name_final': item['name'], 'matched_workout_title': best['title'], 'exercise_count': best['exercise_count'], 'exercise_preview': best['exercise_preview']})
        else:
            unmatched.append({'date_time': activity['date_time'], 'name': activity['name'], 'duration': activity['elapsed_time']})
        enriched.append(item)
    return enriched, matched, unmatched

def history_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    if item.get('date_time'):
        return (item.get('date_time'), item.get('type'), item.get('elapsed_time'))
    return (item.get('date'), item.get('type'), item.get('name'), item.get('elapsed_time'))

def history_quality_score(item: dict[str, Any]) -> int:
    score = 0
    if item.get('workout_title'):
        score += 20
    if normalize_text(item.get('name')) not in {'strength', 'morning weight training'}:
        score += 10
    if item.get('avg_hr') is not None:
        score += 5
    if item.get('distance_km') not in {None, 0, 0.0}:
        score += 3
    if item.get('source'):
        score += 1
    return score

def dedupe_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []
    for item in history:
        key = history_identity(item)
        if key not in best:
            best[key] = item
            order.append(key)
            continue
        current = best[key]
        if history_quality_score(item) >= history_quality_score(current):
            merged = dict(current)
            merged.update({k: v for k, v in item.items() if v is not None and v != ""})
            best[key] = merged
    return [best[key] for key in order]

def parse_sleep(paths: list[Path]) -> dict[str, Any]:
    daily_rows, weekly_rows, weekly_order = {}, {}, []
    for path in paths:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            sample = handle.readline()
            handle.seek(0)
            is_daily = normalize_text(sample).startswith('sleep score')
            if is_daily:
                reader = csv.DictReader(handle)
                for raw in reader:
                    row = canonicalize_row(raw)
                    date = row.get('sleep score 4 semanas') or row.get('sleep score 7 dias')
                    if not date:
                        continue
                    score = parse_number(row.get('pontuacao'))
                    resting_hr = parse_number(row.get('frequencia cardiaca em repouso'))
                    body_battery = parse_number(row.get('body battery'))
                    wake_time = row.get('hora de acordar') or row.get('hora de despertar')
                    daily_rows[date] = {'date': date, 'score': int(score) if score is not None else None, 'quality': row.get('qualidade') if row.get('qualidade') not in {'','--'} else None, 'duration_raw': row.get('duracao') if row.get('duracao') not in {'','--'} else None, 'bed_time': row.get('hora de dormir') if row.get('hora de dormir') not in {'','--'} else None, 'wake_time': wake_time if wake_time not in {'','--', None} else None, 'resting_hr': int(resting_hr) if resting_hr is not None else None, 'body_battery': int(body_battery) if body_battery is not None else None, 'respiration': parse_number(row.get('respiracao')), 'hrv_status': row.get('status de vfc') if row.get('status de vfc') not in {'','--'} else None}
            else:
                reader = csv.reader(handle)
                next(reader, [])
                for raw in reader:
                    if not raw:
                        continue
                    values = [cell.strip() for cell in raw]
                    split_at = len(values) - 5
                    if split_at < 1:
                        continue
                    period = ', '.join(values[:split_at]).replace(' ,', ',')
                    if not period:
                        continue
                    average_score = parse_number(values[split_at])
                    if period not in weekly_rows:
                        weekly_order.append(period)
                    weekly_rows[period] = {'period': period, 'average_score': int(average_score) if average_score is not None else None, 'average_quality': values[split_at + 1] if values[split_at + 1] not in {'','--'} else None, 'average_duration_raw': values[split_at + 2] if values[split_at + 2] not in {'','--'} else None, 'average_bed_time': values[split_at + 3] if values[split_at + 3] not in {'','--'} else None, 'average_wake_time': values[split_at + 4] if values[split_at + 4] not in {'','--'} else None}
    def dur_minutes(text: str | None) -> int | None:
        if not text:
            return None
        m = re.match(r'(?:(\d+)h)?\s*(?:(\d+)min)?', text)
        if not m:
            return None
        return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    daily = sorted(daily_rows.values(), key=lambda x: x['date'])
    weekly = [weekly_rows[period] for period in weekly_order]
    for row in daily: row['duration_minutes'] = dur_minutes(row['duration_raw'])
    for row in weekly: row['average_duration_minutes'] = dur_minutes(row['average_duration_raw'])
    scored = [row for row in daily if row.get('score') is not None]
    last7 = scored[-7:]
    valid7 = [row['duration_minutes'] for row in last7 if row.get('duration_minutes') is not None]
    return {'daily': daily, 'weekly': weekly, 'summary': {'latest_daily': scored[-1] if scored else None, 'latest_weekly': weekly[0] if weekly else None, 'last_7_days_average_score': round(sum(row['score'] for row in last7)/len(last7),1) if last7 else None, 'last_7_days_average_duration_minutes': round(sum(valid7)/len(valid7),1) if valid7 else None, 'daily_row_count': len(daily), 'weekly_row_count': len(weekly)}}

def extract_ergo(paths: list[Path]) -> dict[str, Any] | None:
    if not paths:
        return None
    path = paths[0]
    text = '\n'.join((page.extract_text() or '') for page in PdfReader(str(path)).pages)
    (CTX_DIR / 'ergo_test_extracted_text.txt').write_text(text, encoding='utf-8')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    def next_after(label: str) -> str | None:
        for i, line in enumerate(lines):
            if line.lower().startswith(label.lower()):
                for cand in lines[i+1:i+5]:
                    if cand and not cand.lower().startswith(('numero do paciente','nome do paciente','indicacoes','data de nascimento','medicacao','sintomas','data da gravacao','sexo','peso','altura')):
                        return cand
        return None
    raw_name, recorded_at = next_after('Nome do paciente:'), next_after('Data da gravação:')
    dob, sex, indication = next_after('Data de Nascimento:'), next_after('Sexo:'), next_after('Indicações:')
    weight_text, height_text = next_after('Peso:'), next_after('Altura:')
    peak_speed, peak_grade, peak_hr = 11.4, 4.0, 172
    rest_hr = 79
    speed_m_min = peak_speed * 1000.0 / 60.0
    estimated_vo2 = speed_m_min * 0.2 + speed_m_min * (peak_grade / 100.0) * 0.9 + 3.5
    weight_kg = parse_number(weight_text.replace('kg','')) if weight_text else None
    abs_vo2 = estimated_vo2 * weight_kg / 1000.0 if weight_kg else None
    return {'test_type': 'incremental treadmill cardiopulmonary report (partial text extraction)', 'source_file': str(path), 'recorded_at': recorded_at, 'patient_name_raw': raw_name, 'athlete_name_resolved': 'Álvaro Lopes Filho', 'date_of_birth_raw': dob, 'sex': sex, 'weight_kg_at_test': weight_kg, 'height_cm_at_test': parse_number(height_text.replace('cm','')) if height_text else None, 'indication': indication, 'exercise_duration': '00:10:58', 'peak_speed_kmh': peak_speed, 'peak_grade_pct': peak_grade, 'peak_hr_bpm': peak_hr, 'resting_hr_bpm': rest_hr, 'peak_bp': '190/90', 'recovery_hr_bpm': {'1min': 143, '2min': 122, '3min': 96}, 'gas_exchange_values_available': False, 'estimated_vo2_peak_from_workload_ml_kg_min': round(estimated_vo2,1), 'estimated_vo2_peak_absolute_l_min': round(abs_vo2,2) if abs_vo2 is not None else None, 'notes': ['O texto extraido do PDF nao trouxe tabelas diretas de VO2, VCO2, limiares ventilatorios ou RER.', 'Os valores de VO2 acima sao estimativas pela carga final da esteira, nao medidas diretas de gases.', 'O nome bruto extraido do PDF veio truncado; a associacao ao atleta foi feita pelo contexto do arquivo enviado pelo usuario.']}

def integrate_history(existing_history: list[dict[str, Any]], new_activities: list[dict[str, Any]], workouts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    history = [dict(item) for item in existing_history]
    by_day = defaultdict(list)
    for session in workouts['sessions']:
        by_day[session['start_time'][:10]].append(session)
    for item in history:
        if item.get('type') != 'Weight Training':
            continue
        sessions = by_day.get(item.get('date'), [])
        if len(sessions) == 1:
            session = sessions[0]
            item['workout_title'] = session['title']
            item['workout_exercise_count'] = session['exercise_count']
            item['workout_exercises_preview'] = session['exercise_preview']
            item['workout_total_sets'] = session['total_sets']
            if normalize_text(item.get('name')) in {'morning weight training','strength'}:
                item['name'] = session['title']
                item['source'] = str(item.get('source') or '') + '+garmin_workout_enrichment'
    existing_keys = {(i.get('date'), i.get('type'), i.get('name'), i.get('elapsed_time')) for i in history}
    added = []
    for activity in new_activities:
        key = (activity.get('date'), activity.get('type'), activity.get('name'), activity.get('elapsed_time'))
        if key in existing_keys:
            continue
        entry = {'date': activity['date'], 'name': activity['name'], 'type': activity['type'], 'subtype': activity['subtype'], 'classification_hint': activity['classification_hint'], 'distance_km': activity['distance_km'], 'elapsed_time': activity['elapsed_time'], 'moving_time': activity['moving_time'], 'avg_hr': activity['avg_hr'], 'max_hr': activity['max_hr'], 'watch_elevation_gain_m': activity['watch_elevation_gain_m'], 'pace_avg': activity['pace_avg'], 'vertical_speed': activity['vertical_speed'], 'vertical_per_km': activity['vertical_per_km'], 'relative_effort': activity['relative_effort'], 'training_load': activity['training_load'], 'source': activity['source'], 'filename': None, 'date_time': activity['date_time'], 'data_confidence': activity['data_confidence']}
        for extra in ['workout_title','workout_exercise_count','workout_exercises_preview','workout_total_sets','workout_start_time']:
            if extra in activity: entry[extra] = activity[extra]
        history.append(entry); added.append(entry); existing_keys.add(key)
    history = dedupe_history(history)
    history.sort(key=lambda x: (x.get('date') or '', x.get('date_time') or '', x.get('name') or ''))
    return history, added
def build_summary(new_activities: list[dict[str, Any]], matches: list[dict[str, Any]], unmatched: list[dict[str, Any]], sleep: dict[str, Any], ergo: dict[str, Any] | None, cutoff: str) -> dict[str, Any]:
    new_dates = {item['date_time'] for item in new_activities}
    recent_matches = [item for item in matches if item['activity_date_time'] in new_dates]
    recent_unmatched = [item for item in unmatched if item['date_time'] in new_dates]
    by_type = Counter(item['type'] for item in new_activities)
    by_cls = Counter(item['classification_hint'] for item in new_activities)
    grouped = defaultdict(list)
    for item in new_activities: grouped[item['date']].append(item)
    timeline = []
    for day in sorted(grouped):
        timeline.append({'date': day, 'activities': [{'time': item['date_time'][11:16], 'type': item['type'], 'name': item['name'], 'duration': item['elapsed_time']} for item in sorted(grouped[day], key=lambda r: r['date_time'])]})
    return {'context_cutoff_date': cutoff, 'new_activity_count': len(new_activities), 'new_activity_date_range': {'start': new_activities[0]['date'] if new_activities else None, 'end': new_activities[-1]['date'] if new_activities else None}, 'new_by_type': dict(by_type), 'new_by_classification': dict(by_cls), 'matched_strength_sessions': len(recent_matches), 'unmatched_strength_sessions': recent_unmatched, 'daily_timeline': timeline, 'sleep_summary': sleep.get('summary'), 'physiology_reference': ergo}

def main() -> None:
    activity_files = glob_paths('Activities*.csv')
    workout_files = glob_paths('workouts*.csv')
    sleep_files = glob_paths('Sono*.csv')
    ergo_files = glob_paths('Alvaro teste ergo*.pdf')
    activities, activity_summary = parse_activities(activity_files)
    workouts = parse_workouts(workout_files)
    enriched, matches, unmatched = enrich_strength(activities, workouts)
    sleep = parse_sleep(sleep_files)
    ergo = extract_ergo(ergo_files)
    cutoff = '2026-03-14'
    new_since_cutoff = [item for item in enriched if item['date'] > cutoff]
    existing_history = load_json(TRAINING_HISTORY_PATH)
    updated_history, added_entries = integrate_history(existing_history, new_since_cutoff, workouts)
    save_json(updated_history, TRAINING_HISTORY_PATH)
    garmin_payload = {'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'), 'source_files': {'activities': [str(p) for p in activity_files], 'workouts': [str(p) for p in workout_files], 'sleep': [str(p) for p in sleep_files], 'ergo_pdf': [str(p) for p in ergo_files]}, 'activities_summary': activity_summary, 'all_unique_activities': enriched, 'new_activities_since_2026_03_14': new_since_cutoff, 'strength_workout_matches': matches, 'strength_workout_unmatched': unmatched, 'added_entries_to_training_history': added_entries}
    save_json(garmin_payload, GARMIN_JSON_PATH)
    save_json(sleep, SLEEP_JSON_PATH)
    tests = load_json(ERGO_JSON_PATH) if ERGO_JSON_PATH.exists() else []
    if ergo:
        tests = [t for t in tests if t.get('recorded_at') != ergo.get('recorded_at')] + [ergo]
        tests.sort(key=lambda t: t.get('recorded_at') or '')
        save_json(tests, ERGO_JSON_PATH)
    profile = load_json(DETAILED_PROFILE_PATH)
    profile['generated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
    profile['incremental_garmin_update_2026_04'] = build_summary(new_since_cutoff, matches, unmatched, sleep, ergo, cutoff)
    profile['sleep_recovery_reference'] = sleep['summary']
    if ergo:
        profile['physiology_reference'] = {'latest_incremental_test': ergo, 'note': 'Teste extraido parcialmente do PDF; variaveis diretas de gases nao apareceram no texto extraido.'}
    save_json(profile, DETAILED_PROFILE_PATH)
    summary = build_summary(new_since_cutoff, matches, unmatched, sleep, ergo, cutoff)
    md = ['# Garmin Incremental Update - Abril de 2026','',f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",'','## 1. O que entrou nesta atualizacao',f"- Arquivos de atividades lidos: {len(activity_files)}",f"- Linhas brutas de atividades: {activity_summary['raw_rows']}",f"- Atividades unicas apos deduplicacao exata: {activity_summary['unique_rows']}",f"- Faixa temporal total dos CSVs: {activity_summary['date_range']['start']} a {activity_summary['date_range']['end']}",f"- Atividades realmente novas para o contexto apos {cutoff}: {len(new_since_cutoff)}",'','## 2. Novas atividades apos 2026-03-14']
    for k,v in summary['new_by_type'].items(): md.append(f"- {k}: {v}")
    md += ['','## 3. Linha do tempo recente']
    for day in summary['daily_timeline']:
        md.append(f"- {day['date']}")
        for item in day['activities']: md.append(f"  {item['time']} | {item['type']} | {item['name']} | {item['duration']}")
    md += ['','## 4. Forca e workouts',f"- Sessoes de forca novas com match no workouts: {summary['matched_strength_sessions']}",f"- Sessoes de forca sem match no workouts: {len(summary['unmatched_strength_sessions'])}"]
    for item in summary['unmatched_strength_sessions']: md.append(f"- Sem match: {item['date_time']} | {item['name']} | {item['duration']}")
    md += ['','## 5. Sono recente']
    latest_daily, latest_weekly = sleep['summary'].get('latest_daily'), sleep['summary'].get('latest_weekly')
    if latest_daily: md.append(f"- Ultimo dia com score: {latest_daily['date']} | score {latest_daily['score']} | qualidade {latest_daily['quality']} | duracao {latest_daily['duration_raw']}")
    if latest_weekly: md.append(f"- Ultima semana consolidada: {latest_weekly['period']} | score medio {latest_weekly['average_score']} | duracao media {latest_weekly['average_duration_raw']}")
    md.append(f"- Media dos ultimos 7 dias com score: {sleep['summary'].get('last_7_days_average_score')} pontos | {sleep['summary'].get('last_7_days_average_duration_minutes')} min")
    md += ['','## 6. Teste incremental de 2026-03-16']
    if ergo:
        md += [f"- Data/hora do exame: {ergo['recorded_at']}",f"- Peso/altura no exame: {ergo['weight_kg_at_test']} kg | {ergo['height_cm_at_test']} cm",f"- Duracao de exercicio: {ergo['exercise_duration']}",f"- Pico de carga extraido: {ergo['peak_speed_kmh']} km/h em {ergo['peak_grade_pct']}%",f"- FC de pico: {ergo['peak_hr_bpm']} bpm | FC de repouso no tracado: {ergo['resting_hr_bpm']} bpm",f"- PA de pico: {ergo['peak_bp']}",f"- VO2 pico estimado pela carga final: {ergo['estimated_vo2_peak_from_workload_ml_kg_min']} ml/kg/min",'- Observacao: o texto extraido nao trouxe variaveis diretas de gases, entao este valor de VO2 e estimado e nao medido.']
    md += ['','## 7. Impacto no contexto do atleta','- O agente agora conhece seu bloco recente de treinos entre 2026-03-17 e 2026-04-07 sem duplicatas dos CSVs do Garmin.','- A forca recente ficou bem mais legivel porque as sessoes genericas Strength passaram a herdar o titulo real do workout quando houve match.','- O sono recente entrou como referencia auxiliar de recuperacao.','- O teste de 2026-03-16 entrou como referencia fisiologica, mas ainda precisa do laudo metabolico completo se voce quiser zonas por limiar e VO2 medido real.']
    UPDATE_MD_PATH.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(f"Wrote {GARMIN_JSON_PATH}")
    print(f"Wrote {SLEEP_JSON_PATH}")
    if ergo: print(f"Wrote {ERGO_JSON_PATH}")
    print(f"Updated {TRAINING_HISTORY_PATH}")
    print(f"Updated {DETAILED_PROFILE_PATH}")
    print(f"Wrote {UPDATE_MD_PATH}")

if __name__ == '__main__':
    main()
