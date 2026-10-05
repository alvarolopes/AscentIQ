"""End-to-end personal product routes using exclusively synthetic, temporary data.

Run against the disposable API image with networking disabled. TestClient does
not enter the application lifespan, so no provider sync or background job starts.
"""
import base64
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.server import create_app
from dashboard.snapshot import TZ


class PersonalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.runtime = self.root / "runtime"
        self.day = datetime.now(TZ).date()
        self.headers = {"X-AscentIQ-Request": "1"}
        self.env = patch.dict(os.environ, {"DATABASE_BACKEND": "json", "DASHBOARD_USERNAME": "tester",
            "DASHBOARD_PASSWORD": "synthetic-login-password", "DASHBOARD_SCHEDULE_ENABLED": "false",
            "DASHBOARD_SLEEP_SCHEDULE_ENABLED": "false", "OPENAI_API_KEY": "", "GARMIN_EMAIL": "",
            "GARMIN_PASSWORD": "", "HEVY_API_KEY": "", "DASHBOARD_SECURE_COOKIES": "false"})
        self.env.start()
        self.app = create_app(self.runtime, self.root)
        self.client = TestClient(self.app)
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "tester", "password": "synthetic-login-password"},
                                         headers=self.headers).status_code, 200)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def post(self, path, value, status=200):
        response = self.client.post(path, json=value, headers=self.headers)
        self.assertEqual(response.status_code, status, response.text[:500])
        return response.json()

    def food(self, day, *, kcal=2400, identifier=None, revision=None):
        payload = {"id": identifier or str(uuid.uuid4()), "meal": "Refeição sintética", "text": "Alimentos descritos para teste",
                   "analysis": {"items": [{"name": "Alimentos de exemplo", "kcal": kcal,
                                             "protein_g": 100, "carbs_g": 250, "fat_g": 80}], "notes": "Estimativa sintética"}}
        if revision is not None:
            payload["revision"] = revision
        saved = self.post(f"/api/food/{day}/save", payload)
        return payload, saved

    def complete(self, day, revision):
        return self.post(f"/api/food/{day}/coverage", {"completeness": "complete", "revision": revision})

    def summary(self, day=None):
        response = self.client.get("/api/personal", params={"day": (day or self.day).isoformat()})
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response.json()

    def seed_goal(self):
        effective = (self.day - timedelta(days=30)).isoformat()
        self.post("/api/personal/profile", {"value": {"name": "Pessoa sintética", "age": 42, "height_cm": 180,
                  "weight_kg": 80, "sex": "male", "effective_from": effective}, "revision": 0})
        self.post("/api/personal/preferences", {"value": {"activity_factor": 1.55, "effective_from": effective}, "revision": 1})
        return self.post("/api/personal/goals", {"record": {"id": "synthetic-goal", "type": "fat_loss", "description": "Objetivo sintético",
                     "priority": 1, "target_kcal": 2400, "effective_from": effective}, "revision": 2})

    def seed_review(self):
        self.seed_goal()
        for offset in range(14):
            selected = self.day - timedelta(days=offset)
            _, saved = self.food(selected)
            self.complete(selected, saved["revision"])
        for offset in (13, 9, 5, 0):
            self.post("/api/personal/measurements", {"record": {"id": "measure-" + str(offset),
                      "date": (self.day - timedelta(days=offset)).isoformat(), "weight_kg": 80}})
        return self.post("/api/personal/review", {"day": self.day.isoformat()})

    def test_local_ai_status_and_reviewed_food_without_paid_calls(self):
        self.assertEqual(self.client.get('/api/ai/configuration').status_code, 200)
        self.post('/api/integrations/ai', {'credentials': {'provider': 'ollama', 'local_model': 'gemma3:4b'}})
        self.assertTrue(self.client.get(f'/api/food/{self.day}').json()['configured'])
        pending={'id':str(uuid.uuid4()),'meal':'Lanche','text':'Uma banana de 100 g','analysis':None}
        saved=self.post(f'/api/food/{self.day}/save',pending)
        with patch('dashboard.local_ai.request_text',side_effect=RuntimeError('Ollama local não respondeu')):
            self.post(f'/api/food/{self.day}/analyze',pending,503)
        unchanged=self.client.get(f'/api/food/{self.day}').json()
        self.assertEqual(unchanged['revision'],saved['revision'])
        self.assertEqual(unchanged['pending_count'],1)
        response={'items':[{'name':'Banana 100 g','kcal':89,'protein_g':1.1,'carbs_g':23,'fat_g':0.3}],'notes':'Estimativa sintética.'}
        with patch('dashboard.local_ai.request_text',return_value=json.dumps(response)), patch('dashboard.nutrition.urlopen') as paid:
            analysis=self.post(f'/api/food/{self.day}/analyze',pending)
            self.assertEqual(analysis['source'],'ollama')
            paid.assert_not_called()
        self.assertEqual(self.client.get(f'/api/food/{self.day}').json()['pending_count'],1)
        reviewed=self.post(f'/api/food/{self.day}/save',{**pending,'analysis':analysis,'revision':saved['revision']})
        self.assertEqual(len(reviewed['entries']),1)
        self.assertEqual(reviewed['pending_count'],0)

    def test_saved_pending_estimate_persists_until_review_without_changing_totals(self):
        from dashboard.food_store import FoodDiary
        pending = {'id': str(uuid.uuid4()), 'meal': 'Lanche', 'text': 'Banana de 100 g', 'analysis': None}
        saved = self.post(f'/api/food/{self.day}/save', pending)
        proposal = {'items': [{'name': 'Banana 100 g', 'kcal': 89, 'protein_g': 1.1,
                               'carbs_g': 23, 'fat_g': 0.3}], 'notes': 'Estimativa sintética.',
                    'source': 'ollama', 'model': 'qwen3.5:4b'}
        store = FoodDiary(self.runtime, self.root)
        staged = store.propose(self.day, pending['id'], proposal, expected_revision=saved['revision'])
        self.assertEqual(staged['totals'], saved['totals'])
        self.assertEqual(staged['pending_count'], 1)
        self.assertEqual(staged['entries'][0]['created_at'], saved['entries'][0]['created_at'])
        self.assertEqual(self.client.get(f'/api/food/{self.day}').json()['entries'][0]['analysis_proposal'], proposal)
        with self.assertRaisesRegex(ValueError, 'mudou'):
            store.propose(self.day, pending['id'], {**proposal, 'notes': 'Alterada'}, expected_revision=saved['revision'])
        reviewed = self.post(f'/api/food/{self.day}/save', {**pending, 'analysis': proposal, 'revision': staged['revision']})
        self.assertEqual(reviewed['totals']['kcal'], 89)
        self.assertEqual(reviewed['pending_count'], 0)
        self.assertEqual(len(reviewed['entries']), 1)
        self.assertNotIn('analysis_proposal', reviewed['entries'][0])

    def test_save_automatically_estimates_and_retry_does_not_duplicate(self):
        from dashboard.food_store import FoodDiary
        store = FoodDiary(self.runtime, self.root)
        payload = {'id': str(uuid.uuid4()), 'meal': 'Lanche', 'text': 'Banana de 100 g',
                   'estimate_on_save': True, 'save_token': str(uuid.uuid4()), 'revision': 0}
        analysis = {'items': [{'name': 'Banana 100 g', 'kcal': 89, 'protein_g': 1.1,
                              'carbs_g': 23, 'fat_g': 0.3}], 'notes': 'Estimativa sintética.',
                    'source': 'ollama', 'model': 'qwen3.5:4b'}
        def inference(text, image):
            staged = store.read(self.day)
            self.assertEqual(len(staged['entries']), 1)
            self.assertEqual(staged['pending_count'], 1)
            return analysis
        with patch('dashboard.server.estimate', side_effect=inference) as infer:
            saved = self.post(f'/api/food/{self.day}/save', payload)
            self.assertEqual(saved['analysis_status'], 'estimated')
            self.assertEqual(saved['totals']['kcal'], 89)
            self.assertEqual(saved['entries'][0]['source'], 'ai_estimated')
            retry = self.post(f'/api/food/{self.day}/save', payload)
            self.assertEqual(retry['revision'], saved['revision'])
            self.assertEqual(infer.call_count, 1)
        created = saved['entries'][0]['created_at']
        updated_analysis = {**analysis, 'items': [{**analysis['items'][0], 'name': 'Banana 50 g', 'kcal': 44.5}]}
        with patch('dashboard.server.estimate', return_value=updated_analysis) as infer:
            edited = self.post(f'/api/food/{self.day}/save', {**payload, 'text': 'Banana de 50 g',
                'save_token': str(uuid.uuid4()), 'revision': saved['revision'], 'analysis': analysis})
            infer.assert_called_once_with('Banana de 50 g', None)
        self.assertEqual(len(edited['entries']), 1)
        self.assertEqual(edited['entries'][0]['created_at'], created)
        self.assertEqual(edited['totals']['kcal'], 44.5)

    def test_automatic_save_failure_preserves_pending_meal_and_allows_retry(self):
        payload = {'id': str(uuid.uuid4()), 'meal': 'Lanche', 'text': 'Banana 100 g',
                   'estimate_on_save': True, 'save_token': str(uuid.uuid4()), 'revision': 0}
        with patch('dashboard.server.estimate', side_effect=RuntimeError('Ollama local não respondeu')):
            failed = self.post(f'/api/food/{self.day}/save', payload)
        self.assertEqual(failed['analysis_status'], 'pending')
        self.assertEqual(failed['pending_count'], 1)
        self.assertEqual(failed['unknown_nutrients']['kcal'], 1)
        self.assertEqual(failed['entries'][0]['text'], payload['text'])
        self.assertIsNone(failed['entries'][0]['analysis'])
        analysis = {'items': [{'name': 'Banana 100 g', 'kcal': 89, 'protein_g': 1.1,
                              'carbs_g': 23, 'fat_g': 0.3}], 'notes': '', 'source': 'ollama'}
        with patch('dashboard.server.estimate', return_value=analysis):
            saved = self.post(f'/api/food/{self.day}/save', {**payload, 'revision': failed['revision']})
        self.assertEqual(len(saved['entries']), 1)
        self.assertEqual(saved['pending_count'], 0)
        self.assertEqual(saved['totals']['kcal'], 89)

    def test_automatic_edit_uses_saved_photo_and_does_not_overwrite_concurrent_edit(self):
        from dashboard.food_store import FoodDiary
        image = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'synthetic fixture').decode()
        payload = {'id': str(uuid.uuid4()), 'meal': 'Lanche', 'text': 'Refeição sintética na foto', 'image': image}
        original = self.post(f'/api/food/{self.day}/save', payload)
        analysis = {'items': [{'name': 'Alimento sintético', 'kcal': 100, 'protein_g': 1,
                              'carbs_g': 20, 'fat_g': 2}], 'notes': '', 'source': 'ollama'}
        with patch('dashboard.server.estimate', return_value=analysis) as infer:
            saved = self.post(f'/api/food/{self.day}/save', {**payload, 'image': None,
                'estimate_on_save': True, 'revision': original['revision']})
            infer.assert_called_once_with(payload['text'], image)
        self.assertEqual(saved['entries'][0]['image_id'], original['entries'][0]['image_id'])
        store = FoodDiary(self.runtime, self.root)
        def concurrent_inference(text, photo):
            current = store.read(self.day)
            row = current['entries'][0]
            store.change(self.day, entry={**row, 'text': 'Edição concorrente preservada'}, expected_revision=current['revision'])
            return analysis
        with patch('dashboard.server.estimate', side_effect=concurrent_inference):
            self.post(f'/api/food/{self.day}/save', {**payload, 'image': None,
                'estimate_on_save': True, 'revision': saved['revision']}, 409)
        current = self.client.get(f'/api/food/{self.day}').json()
        self.assertEqual(current['entries'][0]['text'], 'Edição concorrente preservada')
        self.assertIsNone(current['entries'][0]['analysis'])

    def test_daily_targets_are_authenticated_and_included_in_food_diary(self):
        other = TestClient(self.app)
        self.assertEqual(other.get(f'/api/nutrition-targets/{self.day}').status_code, 401)
        other.close()
        self.seed_goal()
        self.post('/api/integrations/ai', {'credentials': {'provider': 'ollama', 'local_model': 'qwen3.5:4b'}})
        output = json.dumps({'energy_adjustment_pct': -0.1, 'protein_g_per_kg': 1.8,
                             'reason': 'Meta sintética para o perfil.', 'limitations': []})
        with patch('dashboard.nutrition_targets.request_text', return_value=output):
            self.app.state.nutrition_targets.refresh(self.day)
        value = self.client.get(f'/api/food/{self.day}').json()
        self.assertEqual(value['targets']['status'], 'ready')
        self.assertEqual(value['targets']['protein_g'], 144)
        self.assertEqual(value['targets']['kcal'], self.summary()['summary']['active_plan']['target_kcal'])

    def test_authentication_csrf_and_personal_validation(self):
        unauthenticated = TestClient(self.app)
        for path in ("/api/personal", "/api/export", "/api/assistant/context", "/api/documents", "/api/integrations"):
            self.assertEqual(unauthenticated.get(path).status_code, 401)
        unauthenticated.close()
        self.assertEqual(self.client.post("/api/personal/profile", json={"value": {"name": "Ignored"}}).status_code, 403)
        saved = self.post("/api/personal/profile", {"value": {"name": "Pessoa sintética", "birth_date": "1990-06-15"}, "revision": 0})
        self.assertEqual(saved["revision"], 1)
        self.post("/api/personal/profile", {"value": {"name": "Stale"}, "revision": 0}, 409)
        self.post("/api/personal/measurements", {"record": {"date": self.day.isoformat(), "weight_kg": -1}}, 400)
        self.assertEqual(self.summary()["state"]["profile"]["name"], "Pessoa sintética")
        self.assertEqual(self.summary()["state"]["profile"]["birth_date"], "1990-06-15")
        self.assertEqual(self.summary()["summary"]["profile"]["birth_date"], "1990-06-15")

    def test_profile_goal_initial_plan_and_dated_measurements(self):
        goal_state = self.seed_goal()
        self.assertEqual(goal_state["goals"][0]["status"], "active")
        self.assertEqual(goal_state["plans"][0]["target_kcal"], 2400)
        self.post("/api/personal/measurements", {"record": {"id": "weight", "date": self.day.isoformat(), "weight_kg": 79.8},
                                                "revision": goal_state["revision"]})
        self.post("/api/personal/checkins", {"record": {"id": "check", "date": self.day.isoformat(), "fatigue": 5, "hunger": 4}})
        summary = self.summary()["summary"]
        self.assertEqual(summary["profile"]["weight_kg"], 79.8)
        self.assertEqual(summary["active_plan"]["target_kcal"], 2400)
        self.assertEqual(summary["energy"]["expenditure_status"], "projected")
        self.assertIsNone(summary["energy"]["deficit_kcal"])

    def test_food_pending_complete_edit_stale_restore_and_retry(self):
        selected = self.day - timedelta(days=1)
        identifier = str(uuid.uuid4())
        _, saved = self.food(selected, kcal=None, identifier=identifier)
        self.assertEqual(saved["pending_count"], 1)
        complete = self.complete(selected, saved["revision"])
        self.assertFalse(complete["complete_nutrition"])
        self.post("/api/personal/energy_records", {"record": {"id": "total", "date": selected.isoformat(),
                    "total_kcal": 2800, "active_kcal": 800, "coverage": "full", "coverage_hours": 24}})
        energy = self.summary(selected)["summary"]["energy"]
        self.assertEqual(energy["pending_count"], 1)
        self.assertIsNone(energy["deficit_kcal"])
        payload, corrected = self.food(selected, kcal=2200, identifier=identifier, revision=complete["revision"])
        self.assertEqual(corrected["completeness"], "partial")
        self.assertEqual(len(corrected["entries"]), 1)
        repeat = self.post(f"/api/food/{selected}/save", payload)
        self.assertEqual(repeat["revision"], corrected["revision"])
        complete = self.complete(selected, corrected["revision"])
        self.assertEqual(self.summary(selected)["summary"]["energy"]["deficit_kcal"], 600)
        self.post(f"/api/food/{selected}/coverage", {"completeness": "partial", "revision": 0}, 409)
        restored = self.post(f"/api/food/{selected}/restore", {"restore_revision": 1, "revision": complete["revision"]})
        self.assertEqual(restored["pending_count"], 1)
        self.assertEqual(len(restored["entries"]), 1)
        self.assertGreater(restored["revision"], complete["revision"])
        self.assertIsNone(self.summary(selected)["summary"]["energy"]["deficit_kcal"])

    def test_empty_day_requires_explicit_fasting_and_removal_reopens_coverage(self):
        empty = self.client.get(f"/api/food/{self.day}").json()
        self.assertEqual(empty["completeness"], "empty")
        self.post(f"/api/food/{self.day}/coverage", {"completeness": "complete", "revision": 0}, 400)
        fasting = self.post(f"/api/food/{self.day}/coverage", {"completeness": "complete", "fasting_declared": True, "revision": 0})
        self.assertTrue(fasting["complete_nutrition"])
        payload, saved = self.food(self.day)
        self.assertEqual(saved["completeness"], "partial")
        self.assertFalse(saved["fasting_declared"])
        complete = self.complete(self.day, saved["revision"])
        removed = self.post(f"/api/food/{self.day}/remove", {"id": payload["id"], "revision": complete["revision"]})
        self.assertEqual(removed["completeness"], "empty")
        self.assertFalse(removed["complete_nutrition"])

    def test_adaptation_acceptance_and_stale_body_change_are_visible(self):
        reviewed = self.seed_review()
        proposal = reviewed["proposal"]
        self.assertEqual(proposal["action"], "adjust")
        self.assertEqual(proposal["suggested_plan"]["target_kcal"], 2300)
        self.post("/api/personal/measurements", {"record": {"id": "measure-0", "date": self.day.isoformat(), "weight_kg": 79.9}})
        self.post(f"/api/personal/proposals/{proposal['id']}/decision", {"decision": "accepted", "day": self.day.isoformat()}, 409)
        saved = self.summary()["state"]
        self.assertEqual(saved["proposals"][0]["status"], "stale")
        self.assertEqual(len(saved["plans"]), 1)
        fresh = self.post("/api/personal/review", {"day": self.day.isoformat()})["proposal"]
        accepted = self.post(f"/api/personal/proposals/{fresh['id']}/decision", {"decision": "accepted", "day": self.day.isoformat()})
        self.assertEqual(accepted["proposal"]["status"], "accepted")
        self.assertEqual(self.summary(self.day + timedelta(days=1))["summary"]["active_plan"]["target_kcal"], 2300)
        self.assertEqual(self.summary()["summary"]["active_plan"]["target_kcal"], 2400)

    def test_assistant_import_uses_selected_period_and_medical_opt_in(self):
        selected = self.day - timedelta(days=2)
        future = self.day + timedelta(days=1)
        (self.root / "data" / "training_history.json").write_text(json.dumps([
            {"date": selected.isoformat(), "type": "Run", "name": "IN_PERIOD_MARKER", "duration_seconds": 1800},
            {"date": future.isoformat(), "type": "Run", "name": "FUTURE_ACTIVITY_MARKER", "duration_seconds": 1800}]))
        (self.root / "data" / "medical_history.json").write_text(json.dumps({"records": [
            {"date": selected.isoformat(), "label": "MEDICAL_PRIVATE_MARKER", "result": "referência sintética"}]}))
        context = self.client.get("/api/assistant/context", params={"day": selected.isoformat(), "days": 2}).json()
        self.assertNotIn("medical", context["context"])
        self.assertNotIn("MEDICAL_PRIVATE_MARKER", context["prompt"])
        self.assertIn("IN_PERIOD_MARKER", context["prompt"])
        self.assertNotIn("FUTURE_ACTIVITY_MARKER", context["prompt"])
        result = self.post("/api/assistant", {"day": selected.isoformat(), "days": 2, "question": "Como foi meu período?",
                    "manual_response": "Resposta sintética importada para revisar o período e suas limitações.", "fingerprint": context["fingerprint"]})
        self.assertEqual(result["source"], "imported")
        self.assertEqual(result["context"]["period"]["to"], selected.isoformat())
        self.assertNotIn("medical", result["scope"])
        opted = self.client.get("/api/assistant/context", params={"day": selected.isoformat(), "days": 2, "include_medical": True}).json()
        self.assertIn("medical", opted["context"])
        self.assertIn("MEDICAL_PRIVATE_MARKER", opted["prompt"])

    def test_assistant_historical_context_excludes_future_plans_and_body(self):
        selected = self.day - timedelta(days=10)
        (self.root / "data" / "body_metrics.json").write_text(json.dumps({"reference_date": self.day.isoformat(),
            "current": {"weight_kg": 80, "notes": "FUTURE_BODY_MARKER"},
            "history": [{"date": self.day.isoformat(), "weight_kg": 80, "label": "FUTURE_BODY_MARKER"}]}))
        self.post("/api/personal/goals", {"record": {"id": "future-goal", "type": "maintenance", "description": "FUTURE_GOAL_MARKER",
                        "effective_from": self.day.isoformat(), "target_kcal": 2300}})
        result = self.client.get("/api/assistant/context", params={"day": selected.isoformat(), "days": 3})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("FUTURE_BODY_MARKER", result.json()["prompt"])
        self.assertNotIn("FUTURE_GOAL_MARKER", result.json()["prompt"])

    def test_export_excludes_credentials_and_contains_user_data(self):
        self.seed_goal()
        self.food(self.day, kcal=2100)
        fake = "synthetic-secret-never-export"
        self.post("/api/integrations/ai", {"credentials": {"api_key": fake, "model": "synthetic-model"}})
        (self.root / ".env").write_text("OPENAI_API_KEY=synthetic-env-secret\n")
        response = self.client.get("/api/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        content = response.json()
        self.assertEqual(content["personal"]["profile"]["name"], "Pessoa sintética")
        self.assertIn(self.day.isoformat(), content["food"])
        for marker in (fake, "synthetic-env-secret", "synthetic-login-password"):
            self.assertNotIn(marker, response.text)
        self.assertNotIn("connections", content)

    def test_document_text_upload_review_and_allowlisted_download(self):
        raw = b"Documento sintetico. Indicador exemplo: 12 unidades."
        payload = {"filename": "../../outside.txt", "content": base64.b64encode(raw).decode(),
                   "label": "Documento sintético", "date": self.day.isoformat()}
        uploaded = self.post("/api/documents", payload)
        self.assertFalse(uploaded["reviewed"])
        self.assertEqual(uploaded["filename"], "outside.txt")
        self.assertEqual(self.post("/api/documents", payload)["id"], uploaded["id"])
        self.assertFalse((self.root / "outside.txt").exists())
        extracted = self.post(f"/api/documents/{uploaded['id']}/extract", {"use_ai": False})
        self.assertIn("draft", extracted)
        reviewed = self.post(f"/api/documents/{uploaded['id']}/review", {"observations": [
            {"name": "Indicador exemplo", "value": "12", "unit": "unidades", "page": 1, "date": self.day.isoformat()}]})
        self.assertTrue(reviewed["reviewed"])
        self.assertEqual(self.client.get(f"/api/documents/{uploaded['id']}/file").content, raw)
        self.assertEqual(self.client.get("/api/documents/unknown/file").status_code, 404)
        self.assertEqual(self.client.get("/api/documents/%2e%2e%2foutside.txt/file").status_code, 404)
        self.post(f"/api/documents/{uploaded['id']}/remove", {})
        self.assertEqual(self.client.get(f"/api/documents/{uploaded['id']}/file").status_code, 404)

    def test_planning_manual_and_csv_imports_are_structured_and_repeatable(self):
        record = {"id": "plan", "date": self.day.isoformat(), "type": "training", "title": "Corrida prevista", "status": "planned"}
        saved = self.post("/api/planning", {"record": record})
        self.assertEqual(saved["status"], "planned")
        self.post("/api/planning", {"record": {**record, "status": "done"}})
        self.assertEqual(len(self.client.get("/api/planning").json()["records"]), 1)
        manual = self.post("/api/import", {"format": "manual", "filename": "manual", "content": json.dumps({
            "id": "manual-1", "date": self.day.isoformat(), "type": "Run", "name": "Corrida sintética", "duration_minutes": 30,
            "distance_km": 5})})
        self.assertEqual(manual["import"]["status"], "complete")
        csv = f"id,date,type,duration_seconds,distance_km\ncsv-1,{self.day},Bike,3600,20\n"
        first = self.post("/api/import", {"format": "csv", "filename": "synthetic.csv", "content": csv})
        repeat = self.post("/api/import", {"format": "csv", "filename": "synthetic.csv", "content": csv})
        self.assertTrue(repeat["repeated"])
        self.assertEqual(first["revision"], repeat["revision"])
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(len(dashboard["activities"]), 2)
        self.assertEqual(sorted(x["duration_seconds"] for x in dashboard["activities"]), [1800, 3600])
        self.post("/api/planning/plan/remove", {})
        self.assertEqual(self.client.get("/api/planning").json()["records"], [])

    def test_missing_document_original_blocks_extraction_before_provider(self):
        # Only the upload signature matters: the original is removed before
        # extraction, and the provider must never receive this fixture.
        raw = b'\x89PNG\r\n\x1a\n' + b'SYNTHETIC IMAGE HEADER'
        uploaded = self.post('/api/documents', {'filename': 'synthetic.png',
            'content': base64.b64encode(raw).decode(), 'date': self.day.isoformat()})
        original = self.app.state.personal_artifacts.document_path(uploaded['id'])
        original.unlink()
        with patch('dashboard.personal_api.request_text') as provider:
            result = self.post(f"/api/documents/{uploaded['id']}/extract", {'use_ai': True}, 400)
        self.assertIn('original', result['detail'])
        provider.assert_not_called()
        self.assertEqual(len(self.app.state.personal_artifacts.read('documents')), 1)

    def test_textual_consent_does_not_authorize_document_or_medical_ai(self):
        uploaded = self.post('/api/documents', {'filename': 'synthetic.txt',
            'content': base64.b64encode(b'Synthetic document only').decode(), 'date': self.day.isoformat()})
        with patch('dashboard.personal_api.request_text') as document_provider, \
                patch('dashboard.assistant.request_text') as assistant_provider:
            self.post(f"/api/documents/{uploaded['id']}/extract", {'use_ai': 'false'}, 400)
            self.post('/api/assistant', {'question': 'Como foi o meu dia?', 'include_medical': 'false'}, 400)
        document_provider.assert_not_called()
        assistant_provider.assert_not_called()
        self.assertEqual(self.client.get('/api/assistant/history').json()['history'], [])


if __name__ == "__main__":
    unittest.main()
