"""Typed request envelopes return uniform pt-BR validation errors.

Synthetic data only; TestClient does not enter the application lifespan.
"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.server import create_app
from dashboard.snapshot import TZ
from dashboard.tests import pg


class SchemaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.runtime = self.root / "runtime"
        self.day = datetime.now(TZ).date()
        self.headers = {"X-AscentIQ-Request": "1"}
        self.env = patch.dict(
            os.environ,
            {
                "DASHBOARD_USERNAME": "tester",
                "DASHBOARD_PASSWORD": "synthetic-login-password",
                "DASHBOARD_SCHEDULE_ENABLED": "false",
                "DASHBOARD_SLEEP_SCHEDULE_ENABLED": "false",
                "OPENAI_API_KEY": "",
                "GARMIN_EMAIL": "",
                "GARMIN_PASSWORD": "",
                "HEVY_API_KEY": "",
                "DASHBOARD_SECURE_COOKIES": "false",
            },
        )
        self.env.start()
        self.client = TestClient(create_app(self.runtime, self.root))
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "tester", "password": "synthetic-login-password"},
                headers=self.headers,
            ).status_code,
            200,
        )

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def post(self, path, value):
        return self.client.post(path, json=value, headers=self.headers)

    def test_validation_error_is_400_with_portuguese_detail(self):
        response = self.post("/api/documents/synthetic/extract", {"use_ai": "false"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "use_ai: informe verdadeiro ou falso.")

    def test_missing_field_names_the_field(self):
        response = self.post("/api/import/reconcile", {})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["detail"].startswith("action: campo obrigatório"), response.json()["detail"])

    def test_reconcile_requires_record_identifier(self):
        response = self.post("/api/import/reconcile", {"action": "keep"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Informe o registro a reconciliar.")

    def test_extra_fields_are_ignored(self):
        response = self.post(
            "/api/personal/profile", {"value": {"name": "Pessoa sintética"}, "unknown_field": {"nested": True}}
        )
        self.assertEqual(response.status_code, 200, response.text[:500])

    def test_server_models_also_return_400(self):
        response = self.post(f"/api/food/{self.day}/save", {"text": 1})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["detail"].startswith("text:"), response.json()["detail"])

    def test_domain_messages_preserved(self):
        response = self.post("/api/assistant", {"question": "Como foi o meu dia?", "days": 120})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Use um período de 1 a 90 dias.")
        response = self.post("/api/personal/measurements", {"record": {"date": self.day.isoformat(), "weight_kg": -1}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "weight_kg: informe um número entre 20 e 500.")


if __name__ == '__main__':
    unittest.main()
