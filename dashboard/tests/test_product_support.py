import base64
import contextlib
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard.artifacts import Artifacts
from dashboard.food_store import FoodDiary
from dashboard.nutrition import validate
from dashboard.provider_settings import ProviderSettings
from dashboard.tests import pg


class ProductSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.day = date(2026, 10, 1)

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_diary_pending_complete_and_recovery(self):
        legacy = self.runtime / 'food-diary'
        legacy.mkdir()
        original = [
            {
                'id': 'legacy',
                'text': 'A meal',
                'analysis': validate(
                    {'items': [{'name': 'Synthetic food', 'kcal': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 15}]}
                ),
            }
        ]
        (legacy / '2026-10-01.json').write_text(json.dumps(original))
        diary = FoodDiary(self.runtime, self.root)
        self.assertEqual(diary.read(self.day)['totals']['kcal'], 500)
        saved = diary.change(self.day, entry={'id': 'pending', 'analysis': None, 'text': 'Unknown portion'})
        complete = diary.change(self.day, completeness='complete', expected_revision=saved['revision'])
        self.assertEqual(complete['pending_count'], 1)
        self.assertFalse(complete['complete_nutrition'])
        self.assertEqual(complete['totals']['kcal'], 500)
        restored = diary.change(self.day, restore_revision=0, expected_revision=complete['revision'])
        self.assertEqual(restored['entries'], original)
        self.assertEqual(FoodDiary(self.runtime, self.root).read(self.day)['revision'], restored['revision'])

    def test_read_many_matches_read_and_uses_single_query(self):
        diary = FoodDiary(self.runtime, self.root)
        days = [self.day - timedelta(days=offset) for offset in range(14)]
        for selected in days[:3]:
            diary.change(
                selected,
                entry={
                    'id': 'meal-' + selected.isoformat(),
                    'text': 'Synthetic',
                    'analysis': {'items': [{'name': 'Food', 'kcal': 400, 'protein_g': 20, 'carbs_g': 50, 'fat_g': 10}]},
                },
            )
        legacy = self.runtime / 'food-diary'
        (legacy / (days[5].isoformat() + '.json')).write_text(
            json.dumps(
                [
                    {
                        'id': 'legacy',
                        'text': 'Legacy meal',
                        'analysis': {
                            'items': [{'name': 'Food', 'kcal': 300, 'protein_g': 15, 'carbs_g': 40, 'fat_g': 8}]
                        },
                    }
                ]
            )
        )
        expected = {selected: diary.read(selected) for selected in days}
        original_db = diary._db
        counters = []

        class Counting:
            def __init__(self, conn):
                self.conn = conn
                self.selects = 0

            def execute(self, query, values=()):
                if 'food_diary_state' in query and query.lstrip().upper().startswith('SELECT'):
                    self.selects += 1
                return self.conn.execute(query, values)

            def __getattr__(self, name):
                return getattr(self.conn, name)

        @contextlib.contextmanager
        def counting_db():
            with original_db() as conn:
                counter = Counting(conn)
                counters.append(counter)
                yield counter

        with patch.object(diary, '_db', counting_db):
            self.assertEqual(diary.read_many(days), expected)
        self.assertEqual(sum(counter.selects for counter in counters), 1)

    def test_edit_retry_and_conflicting_edit(self):
        diary = FoodDiary(self.runtime, self.root)
        entry = {'id': 'same', 'text': 'Synthetic', 'analysis': None}
        saved = diary.change(self.day, entry=entry, expected_revision=0)
        retry = diary.change(self.day, entry=entry, expected_revision=0)
        self.assertEqual(saved['revision'], retry['revision'])
        with self.assertRaises(ValueError):
            diary.change(self.day, entry={**entry, 'text': 'Changed'}, expected_revision=0)
        self.assertEqual(diary.read(self.day)['entries'][0]['text'], 'Synthetic')

    def test_no_meals_is_not_fasting_and_unknown_calories_are_not_zero(self):
        diary = FoodDiary(self.runtime, self.root)
        self.assertEqual(diary.read(self.day)['completeness'], 'empty')
        self.assertFalse(diary.read(self.day)['complete_nutrition'])
        with self.assertRaises(ValueError):
            diary.change(self.day, completeness='complete')
        result = diary.change(self.day, completeness='complete', fasting_declared=True)
        self.assertTrue(result['complete_nutrition'])
        unknown = validate({'items': [{'name': 'Unknown food', 'kcal': None}]}, allow_unknown=True)
        self.assertIsNone(unknown['items'][0]['kcal'])

    def test_credentials_encrypted_and_status_never_contains_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = ProviderSettings(self.runtime)
            settings.configure('hevy', {'api_key': 'synthetic-test-key'})
            self.assertNotIn('synthetic-test-key', json.dumps(settings.status()))
            self.assertNotIn(b'synthetic-test-key', settings.path.read_bytes())
            self.assertIsNone(os.environ.get('HEVY_API_KEY'))
            self.assertEqual(ProviderSettings(self.runtime).credentials('hevy'), {'api_key': 'synthetic-test-key'})
            settings.configure('hevy', enabled=False)
            self.assertEqual(ProviderSettings(self.runtime).credentials('hevy'), {})
            with self.assertRaises(ValueError):
                settings.configure('hevy', {'arbitrary_env': 'not-allowed'})

    def test_documents_are_content_addressed_private_and_versioned(self):
        artifacts = Artifacts(self.runtime, self.root)
        raw = base64.b64encode(b'Synthetic result: 123 units.').decode()
        saved = artifacts.upload_document('../../outside.txt', raw, 'Synthetic reference', '2026-10-01')
        self.assertEqual(artifacts.document_path(saved['id']).parent, artifacts.folder)
        repeated = artifacts.upload_document('different.txt', raw, 'Another', '2026-10-01')
        self.assertEqual(repeated['id'], saved['id'])
        artifacts.save('documents', {**saved, 'reviewed': True, 'observations': [{'name': 'Example', 'value': 123}]})
        self.assertTrue(any(key.startswith('documents:history:') for key in artifacts.export()))
        self.assertIsNone(artifacts.document_path('../../outside'))
        with self.assertRaises(ValueError):
            artifacts.upload_document('payload.html', raw, 'Invalid', '2026-10-01')


if __name__ == '__main__':
    unittest.main()
