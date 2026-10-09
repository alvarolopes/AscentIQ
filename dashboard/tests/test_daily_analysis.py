import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.daily_analysis import DailyReports, ask_llm, prepare
from dashboard.server import create_app
from dashboard.tests import test_dashboard


def fixture():
    return {"activities": [
        {"id":"run", "date":"2026-09-30", "kind":"running", "distance_km":8},
        {"id":"g1", "date":"2026-09-30", "kind":"strength", "avg_hr":100},
        {"id":"future", "date":"2026-10-01", "kind":"running"}],
        "strength":[{"id":"h1", "date":"2026-09-30", "garmin_activity_ids":["g1"],
                     "exercises":[{"name":"Squat", "notes":"private-note", "sets":[{"reps":8,"weight_kg":40,"rpe":7}]}]},
                    {"id":"h2", "date":"2026-09-30", "exercises":[]}],
        "performance":{"series":[{"date":"2026-09-24","daily_load":12},
                                   {"date":"2026-10-01","daily_load":90}]},
        "medical":{"secret":"private-exam"},"body":{"secret":"private-body"}}


class DailyTests(unittest.TestCase):
    def test_context_dates_deduplication_and_privacy(self):
        result = prepare(fixture(), date(2026,9,30))
        self.assertEqual(result["context"]["session_count"],3)
        self.assertEqual(len(result["context"]["activities"]),1)
        self.assertEqual(result["context"]["strength"][0]["cardio_records"][0]["avg_hr"],100)
        self.assertEqual(result["context"]["strength"][0]["exercises"][0]["sets"][0]["rpe"],7)
        for marker in ("future", "2026-10-01", "private-exam", "private-body", "private-note"):
            self.assertNotIn(marker,result["prompt"])

    def test_persistence_cache_changes_and_failed_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DailyReports(Path(folder))
            prepared = prepare(fixture(),date(2026,9,30))
            with patch('dashboard.daily_analysis.ask_llm',return_value='Relatório de teste completo.') as llm:
                original = store.save(prepared)
                self.assertEqual(store.save(prepared),original)
                self.assertEqual(llm.call_count,1)
            snapshot = fixture()
            snapshot['activities'][0]['distance_km'] = 10
            changed = prepare(snapshot,date(2026,9,30))
            self.assertNotEqual(changed['fingerprint'],prepared['fingerprint'])
            with patch('dashboard.daily_analysis.ask_llm',side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError): store.save(changed)
            self.assertEqual(DailyReports(Path(folder)).read(date(2026,9,30)),original)
            imported = store.save(changed,'Resposta importada de outra IA.')
            self.assertEqual(imported['source'],'manual')
            self.assertEqual(imported['fingerprint'],changed['fingerprint'])

    def test_empty_day_and_missing_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError): ask_llm('test')
            with self.assertRaises(ValueError): DailyReports(Path(folder)).save(prepare({},date(2026,9,30)))

    def test_provider_contract_and_incomplete_response(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}):
            response = {'status':'completed','output':[{'type':'reasoning'},{'type':'message','content':[{'type':'output_text','text':'Analysis'}]}]}
            with patch('dashboard.daily_analysis.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as call:
                self.assertEqual(ask_llm('prompt'),'Analysis')
                payload = json.loads(call.call_args.args[0].data)
                self.assertFalse(payload['store'])
                self.assertEqual(call.call_args.kwargs['timeout'],45)
            with patch('dashboard.daily_analysis.urlopen',return_value=io.BytesIO(b'{"status":"incomplete"}')):
                with self.assertRaises(RuntimeError): ask_llm('prompt')


class DailyApiTests(test_dashboard.Fixture):
    def login(self):
        return self.client.post("/api/auth/login", json={"username":"alvaro","password":"test-only-password"}, headers={"X-AscentIQ-Request":"1"})

    def setUp(self):
        super().setUp()
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD":"test-only-password", "DASHBOARD_USERNAME":"alvaro"}):
            self.client = TestClient(create_app(self.runtime,self.root))

    def tearDown(self):
        self.client.close()
        super().tearDown()
    def test_daily_auth_dates_import_and_stale_input(self):
        url = '/api/daily-analysis/2026-09-30'
        self.assertEqual(self.client.get(url).status_code,401)
        self.login()
        self.assertEqual(self.client.get('/api/daily-analysis/invalid').status_code,400)
        self.save('training_history',[{'date':'2026-09-30','type':'Run','distance_km':8}])
        preview = self.client.get(url).json()
        body = {'fingerprint':preview['fingerprint'],'text':'Relatório importado para este treino.'}
        self.assertEqual(self.client.post(url,json=body).status_code,403)
        headers = {'X-AscentIQ-Request':'1'}
        self.assertEqual(self.client.post(url,json=body,headers=headers).status_code,200)
        self.assertEqual(self.client.get(url).json()['report']['source'],'manual')
        self.save('training_history',[{'date':'2026-09-30','type':'Run','distance_km':10}])
        self.assertTrue(self.client.get(url).json()['stale'])
        self.assertEqual(self.client.post(url,json=body,headers=headers).status_code,409)
