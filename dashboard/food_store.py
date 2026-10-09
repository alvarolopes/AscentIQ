"""Versioned food diary, with explicit coverage and lazy legacy migration."""
from __future__ import annotations

import copy
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

from dashboard.repository import operational_db, postgres_enabled

FIELDS = ('kcal', 'protein_g', 'carbs_g', 'fat_g')


class FoodDiary:
    def __init__(self, runtime: Path, root: Path | None = None):
        self.runtime = Path(runtime)
        self.root = Path(root) if root is not None else self.runtime
        self.folder = self.runtime / 'food-diary'
        self.folder.mkdir(parents=True, exist_ok=True)
        if not postgres_enabled(self.root):
            with self._db() as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS food_diary_state (day TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def _db(self):
        return operational_db(self.runtime, 'food', self.root)

    def _load(self, conn, day):
        row = conn.execute('SELECT payload FROM food_diary_state WHERE day=?', (day.isoformat(),)).fetchone()
        if row:
            return json.loads(row[0])
        return self._legacy(day)

    def _legacy(self, day):
        path = self.folder / (day.isoformat() + '.json')
        legacy = json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda _: None) if path.exists() else []
        if isinstance(legacy, dict):
            return legacy
        return {'revision': 0, 'entries': legacy, 'completeness': 'partial' if legacy else 'empty',
                'fasting_declared': False, 'history': []}

    @staticmethod
    def _view(day, state):
        entries = copy.deepcopy(state.get('entries', []))
        known = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 20000 and math.isfinite(value)
        # Old files are observations, not evidence of valid nutrients. Quarantine
        # malformed/missing numbers in the view rather than showing them as zero.
        for entry in entries:
            analysis = entry.get('analysis')
            if not isinstance(analysis, dict) or not isinstance(analysis.get('items'), list):
                entry['analysis'] = None
                continue
            if any(not isinstance(item, dict) for item in analysis['items']):
                entry['analysis'] = None
                continue
            for item in analysis['items']:
                for field in FIELDS:
                    if not known(item.get(field)):
                        item[field] = None
        pending = sum(1 for entry in entries if not (entry.get('analysis') or {}).get('items') or
                      any(item.get('kcal') is None for item in entry['analysis']['items']))
        totals = {key: round(sum(item[key] for entry in entries
                  for item in (entry.get('analysis') or {}).get('items', [])
                  if known(item.get(key))), 1) for key in FIELDS}
        unknown = {key: sum(1 for entry in entries if not (entry.get('analysis') or {}).get('items') or
                   any(item.get(key) is None for item in entry['analysis']['items'])) for key in FIELDS}
        complete = state.get('completeness', 'partial' if entries else 'empty')
        return {'date': day.isoformat(), 'entries': entries, 'totals': totals,
                'revision': state.get('revision', 0), 'completeness': complete,
                'coverage': complete, 'pending_count': pending, 'unknown_nutrients': unknown,
                'fasting_declared': bool(state.get('fasting_declared')),
                'complete_nutrition': complete == 'complete' and pending == 0 and
                    (bool(entries) or bool(state.get('fasting_declared'))),
                'history': [{k: x[k] for k in ('revision', 'action', 'at') if k in x}
                            for x in state.get('history', [])]}

    def read(self, day: date):
        return self.read_many([day])[day]

    def read_many(self, days):
        days = list(days)
        if not days:
            return {}
        with self._db() as conn:
            if postgres_enabled(self.root):
                rows = conn.execute('SELECT day,payload FROM food_diary_state WHERE day = ANY(%s)',
                                    ([selected.isoformat() for selected in days],)).fetchall()
            else:
                marks = ','.join('?' for _ in days)
                rows = conn.execute(f'SELECT day,payload FROM food_diary_state WHERE day IN ({marks})',
                                    tuple(selected.isoformat() for selected in days)).fetchall()
            stored = {row['day']: json.loads(row['payload']) for row in rows}
            key = lambda selected: selected.isoformat()
            return {selected: self._view(selected, stored[key(selected)] if key(selected) in stored
                                         else self._legacy(selected)) for selected in days}

    def propose(self, day, identifier, analysis, *, expected_revision):
        """Persist an estimate for review without changing recorded nutrients."""
        from dashboard.nutrition import validate
        current = self.read(day)
        entry = next((row for row in current['entries'] if row['id'] == identifier), None)
        if entry is None:
            raise ValueError('Refeição não encontrada.')
        if entry.get('analysis') and all(item.get('kcal') is not None for item in entry['analysis']['items']):
            raise ValueError('A refeição já possui valores registrados.')
        return self.change(day, entry={**entry, 'analysis_proposal': validate(analysis)},
                           expected_revision=expected_revision)

    def change(self, day, entry=None, remove=None, *, expected_revision=None,
               completeness=None, fasting_declared=False, restore_revision=None):
        if not isinstance(fasting_declared, bool):
            raise ValueError('Jejum declarado deve ser verdadeiro ou falso.')
        with self._db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._load(conn, day)
            if entry is not None:
                present = next((x for x in state['entries'] if x['id'] == entry['id']), None)
                comparable = lambda x: {k: v for k, v in x.items() if k not in ('created_at', 'updated_at')}
                if present and comparable(present) == comparable(entry):
                    return self._view(day, state)
            if expected_revision is not None and expected_revision != state.get('revision', 0):
                raise ValueError('O diário mudou. Atualize o dia antes de salvar a correção.')
            old = copy.deepcopy(state)
            action = 'save'
            if restore_revision is not None:
                previous = next((x for x in state.get('history', []) if x['revision'] == restore_revision), None)
                if previous is None:
                    raise ValueError('Versão anterior não encontrada.')
                state.update(copy.deepcopy(previous['state']))
                action = 'restore'
            elif remove is not None:
                state['entries'] = [x for x in state['entries'] if x['id'] != remove]
                state['completeness'] = 'partial' if state['entries'] else 'empty'
                state['fasting_declared'] = False
                action = 'remove'
            elif entry is not None:
                present = next((x for x in state['entries'] if x['id'] == entry['id']), None)
                if present:
                    # A retry must preserve the original timestamps and not create another revision.
                    comparable = lambda x: {k: v for k, v in x.items() if k not in ('created_at', 'updated_at')}
                    if comparable(present) == comparable(entry):
                        return self._view(day, state)
                    entry = {**entry, 'created_at': present.get('created_at'),
                             'updated_at': datetime.now(UTC).isoformat()}
                    state['entries'] = [entry if x['id'] == entry['id'] else x for x in state['entries']]
                    action = 'edit'
                else:
                    state['entries'].append(entry)
                state['completeness'] = 'partial'
                state['fasting_declared'] = False
            if completeness is not None:
                if completeness not in ('complete', 'partial', 'empty'):
                    raise ValueError('Estado do diário inválido.')
                if completeness == 'complete' and not state['entries'] and not fasting_declared:
                    raise ValueError('Um dia vazio só pode ser completo com jejum declarado.')
                if fasting_declared and state['entries']:
                    raise ValueError('Jejum declarado é incompatível com refeições registradas.')
                state['completeness'] = completeness
                state['fasting_declared'] = bool(fasting_declared)
                action = 'coverage'
            relevant = lambda s: {k: s.get(k) for k in ('entries', 'completeness', 'fasting_declared')}
            if relevant(old) == relevant(state):
                return self._view(day, state)
            state['history'] = old.get('history', []) + [{'revision': old.get('revision', 0),
                'state': relevant(old), 'action': action, 'at': datetime.now(UTC).isoformat()}]
            state['revision'] = old.get('revision', 0) + 1
            conn.execute('INSERT INTO food_diary_state(day,payload) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET payload=excluded.payload',
                         (day.isoformat(), json.dumps(state, ensure_ascii=False, allow_nan=False)))
            return self._view(day, state)

    def export(self):
        with self._db() as conn:
            days = {row[0] for row in conn.execute('SELECT day FROM food_diary_state')}
            days.update(path.stem for path in self.folder.glob('*.json')
                        if len(path.stem) == 10)
            return {key: self._load(conn, date.fromisoformat(key)) for key in sorted(days)}
