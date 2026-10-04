"""Dated sleep observations; missing scores never erase measured duration."""
from datetime import date, timedelta

FIELDS = ('date', 'score', 'quality', 'duration_minutes', 'duration_raw',
          'bed_time', 'wake_time', 'resting_hr', 'body_battery', 'respiration', 'hrv_ms', 'hrv_status')


def sleep_rows(sleep, reference_date=None):
    rows = {}
    for record in sleep.get('daily', []):
        try:
            day = date.fromisoformat(record.get('date', '')).isoformat()
        except (ValueError, TypeError):
            continue
        if reference_date and day > reference_date:
            continue
        if not any(record.get(k) is not None for k in FIELDS if k != 'date'):
            continue
        rows[day] = {k: record.get(k) for k in FIELDS}
    return [rows[day] for day in sorted(rows)]


def summarize_sleep(sleep, reference_date=None):
    rows = sleep_rows(sleep, reference_date)
    latest = rows[-1] if rows else None
    scored = [r for r in rows if r.get('score') is not None]
    durations = [r for r in rows if r.get('duration_minutes') is not None]
    end = reference_date or (latest['date'] if latest else None)
    start = (date.fromisoformat(end) - timedelta(days=6)).isoformat() if end else None
    window = [r for r in rows if start <= r['date'] <= end] if end else []
    def average(field):
        values = [r[field] for r in window if r.get(field) is not None]
        return round(sum(values) / len(values), 1) if values else None
    return {'latest_daily': latest, 'latest_scored_daily': scored[-1] if scored else None,
            'latest_duration_daily': durations[-1] if durations else None,
            'last_7_days_average_score': average('score'),
            'last_7_days_average_duration_minutes': average('duration_minutes'),
            'last_7_days_score_count': sum(r.get('score') is not None for r in window),
            'last_7_days_duration_count': sum(r.get('duration_minutes') is not None for r in window),
            'window_start': start, 'window_end': end}
