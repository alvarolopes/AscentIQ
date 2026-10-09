"""Focused regressions using temporary data and no external provider requests."""

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from dashboard import settings
from dashboard.artifacts import Artifacts
from dashboard.assistant import answer
from dashboard.food_store import FoodDiary
from dashboard.pipeline import rebuild
from dashboard.provider_settings import ProviderSettings
from dashboard.tests import pg


class BackendSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.day = date(2026, 10, 3)
        self._settings = settings.override(runtime=self.runtime)
        self._settings.__enter__()
        self.addCleanup(self._settings.__exit__, None, None, None)

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_empty_invalid_items_remain_pending(self):
        diary = FoodDiary(self.runtime, self.root)
        entries = [
            {'id': 'empty', 'analysis': {'items': []}},
            {'id': 'invalid', 'analysis': {'items': [{'name': 'synthetic', 'kcal': -3, 'protein_g': True}]}},
            {'id': 'not-object', 'analysis': {'items': ['invalid']}},
        ]
        (diary.folder / (self.day.isoformat() + '.json')).write_text(
            json.dumps({'entries': entries, 'completeness': 'complete', 'history': [], 'revision': 0})
        )
        result = diary.read(self.day)
        self.assertEqual(result['pending_count'], 3)
        self.assertFalse(result['complete_nutrition'])
        self.assertIsNone(result['entries'][1]['analysis']['items'][0]['kcal'])

    def test_invalid_document_does_not_leave_blob_and_repeat_preserves_review(self):
        store = Artifacts(self.runtime, self.root)
        with self.assertRaises(ValueError):
            store.upload_document(
                'invalid.pdf', base64.b64encode(b'%PDF-not-a-document').decode(), '', self.day.isoformat()
            )
        self.assertEqual(list(store.folder.iterdir()), [])
        content = base64.b64encode(b'Synthetic reference only').decode()
        record = store.upload_document('reference.txt', content, 'Reference', self.day.isoformat())
        store.save('documents', {**record, 'reviewed': True, 'observations': [{'name': 'Synthetic', 'value': '42'}]})
        repeated = store.upload_document('reference.txt', content, '', self.day.isoformat())
        self.assertTrue(repeated['reviewed'])
        self.assertEqual(len(store.read('documents')), 1)

    def test_provider_configuration_rejects_truthy_strings(self):
        store = ProviderSettings(self.runtime)
        with self.assertRaises(ValueError):
            store.configure('ai', {'api_key': 'synthetic'}, enabled='false')
        with self.assertRaises(ValueError):
            store.configure('ai', ['api_key'])
        self.assertFalse(store.path.exists())

    def test_empty_rebuild_never_runs_scripts_or_uses_samples(self):
        (self.root / 'data').mkdir()
        (self.root / 'data' / 'sample_training_history.json').write_text('[{"date":"2026-10-01","type":"Run"}]')
        with patch('dashboard.pipeline.run_script') as run:
            rebuild(self.root)
        run.assert_not_called()
        result = json.loads((self.root / 'data' / 'performance_management_model.json').read_text())
        self.assertEqual(result['summary'], {})
        self.assertEqual(result['daily_series'], [])

    def prepared(self):
        return {
            'fingerprint': 'synthetic-context',
            'prompt': 'Synthetic data only',
            'context': {'profile': {'timezone': 'America/Sao_Paulo'}},
            'scope': ['profile'],
        }

    def test_concurrent_assistant_requests_reuse_one_provider_call(self):
        store = Artifacts(self.runtime, self.root)
        with patch('dashboard.assistant.request_text', return_value='Synthetic response') as provider:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(lambda _: answer(store, self.prepared(), 'Same synthetic question', self.day), range(2))
                )
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(results[0]['id'], results[1]['id'])
        self.assertEqual(len(store.read('assistant')), 1)

    def test_assistant_quota_uses_personal_timezone_at_midnight(self):
        store = Artifacts(self.runtime, self.root)
        fixed = datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
        store.save('assistant', {'id': 'earlier', 'source': 'openai', 'created_at': '2026-10-03T23:00:00+00:00'})

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        with patch('dashboard.assistant.datetime', Clock), patch('dashboard.assistant.request_text') as provider:
            with self.assertRaises(ValueError):
                answer(store, self.prepared(), 'Different question', self.day, daily_limit=1)
        provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
