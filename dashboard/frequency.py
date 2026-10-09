"""Count daily records while deduplicating linked strength sessions."""
from datetime import date, timedelta

from scripts.sleep_data import sleep_rows


def frequency(snapshot, food, year):
    rows: dict[str, dict] = {}
    current, end = date(year, 1, 1), date(year, 12, 31)
    while current <= end:
        key = current.isoformat()
        rows[key] = dict(date=key,count=0,sleep_minutes=None,meal_count=0,kcal=None,pending_count=0,running_count=0,running_km=None,strength_count=0)
        current += timedelta(days=1)
    for sleep in sleep_rows(snapshot.get('sleep', {}), end.isoformat()):
        row = rows.get(sleep.get('date'))
        if row is not None and (sleep.get('duration_minutes') is not None or sleep.get('score') is not None):
            row['sleep_minutes'], row['count'] = sleep.get('duration_minutes'), 1
    linked = {str(i) for s in snapshot.get('strength', []) for i in s.get('garmin_activity_ids', [])}
    for session in snapshot.get('strength', []):
        if session.get('date') in rows:
            rows[session['date']]['strength_count'] += 1
    for activity in snapshot.get('activities', []):
        row = rows.get(activity.get('date'))
        if row is None or str(activity.get('id')) in linked:
            continue
        if activity.get('kind') == 'running':
            row['running_count'] += 1
            if activity.get('distance_km') is not None:
                row['running_km'] = (row['running_km'] or 0) + activity['distance_km']
        elif activity.get('kind') == 'strength':
            row['strength_count'] += 1
    for key,state in food.items():
        row = rows.get(key)
        if row is None:
            continue
        entries = state.get('entries', [])
        values: list[float] = []
        row['meal_count'] = len(entries)
        for entry in entries:
            items = (entry.get('analysis') or {}).get('items', [])
            row['pending_count'] += int(not items or any(i.get('kcal') is None for i in items))
            values.extend(i['kcal'] for i in items if isinstance(i.get('kcal'), (int,float)))
        row['kcal'] = round(sum(values),1) if values else None
    for row in rows.values():
        row['count'] += sum(int(row[key] > 0) for key in ('meal_count', 'running_count', 'strength_count'))
        if row['running_km'] is not None:
            row['running_km'] = round(row['running_km'],2)
    return {'year':year,'days':list(rows.values())}
