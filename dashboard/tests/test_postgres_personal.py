"""Personal stores against an explicitly disposable PostgreSQL database.

Never reads project datasets, credentials, or production state. No schema/table
deletion is performed. The maintenance runner owns disposable database cleanup.
"""

import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from dashboard import repository
from dashboard.artifacts import Artifacts
from dashboard.food_store import FoodDiary
from dashboard.health import ConflictError, HealthStore
from dashboard.imports import ImportService
from dashboard.tests import pg


class PostgresPersonalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)
        self.root = repository.ROOT
        self.prefix = "pg-personal-" + uuid.uuid4().hex
        # A distinct old date is a key for the synthetic diary, not a real observation.
        self.day = date(
            1980 + int(self.prefix[-2:], 16) % 20,
            1 + int(self.prefix[-4:-2], 16) % 12,
            1 + int(self.prefix[-6:-4], 16) % 28,
        )
        self.health = HealthStore(self.runtime, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def publish_synthetic(self):
        repo = repository.PostgresRepository()
        files = {
            "data/athlete_profile.json": json.dumps({"name": self.prefix}).encode(),
            "data/training_history.json": b"[]",
            "data/hevy_workouts.json": b"[]",
            "data/strength_training_consolidated.json": b"[]",
            "data/daily_energy.json": json.dumps(
                {
                    "schema_version": 1,
                    "daily": [
                        {
                            "date": self.day.isoformat(),
                            "total_kcal": 2800,
                            "active_kcal": 800,
                            "coverage": "complete",
                            "source": "synthetic_garmin",
                            "method": "wearable_total",
                        }
                    ],
                }
            ).encode(),
        }
        return repo.publish(files, reason=self.prefix, expected=repo.active())

    def test_energy_reads_active_postgres_dataset_not_local_json(self):
        self.publish_synthetic()
        diary = FoodDiary(self.runtime, self.root)
        entry = {
            "id": self.prefix,
            "text": "Synthetic meal",
            "analysis": {
                "items": [{"name": "Synthetic food", "kcal": 2200, "protein_g": 100, "carbs_g": 250, "fat_g": 80}]
            },
        }
        saved = diary.change(self.day, entry=entry)
        diary.change(self.day, completeness="complete", expected_revision=saved["revision"])
        summary = self.health.summary(self.day, {}, diary)
        self.assertEqual(summary["energy"]["source"], "synthetic_garmin")
        self.assertEqual(summary["energy"]["expenditure_kcal"], 2800)
        self.assertEqual(summary["energy"]["deficit_kcal"], 600)
        self.assertFalse((self.runtime / "health.sqlite").exists())
        self.assertFalse((self.runtime / "food.sqlite").exists())

    def test_health_roundtrip_conflicting_clients_and_publication_rollback(self):
        before = self.health.read()
        saved = self.health.save(
            "measurements", {"id": self.prefix, "date": self.day.isoformat(), "weight_kg": 80}, before["revision"]
        )
        restored = HealthStore(self.runtime, self.root).read()
        self.assertEqual(restored["revision"], saved["revision"])
        self.assertTrue(any(row["id"] == self.prefix for row in restored["measurements"]))
        self.assertEqual(self.health.read(before["revision"]), before)
        expected = saved["revision"]

        def client(name):
            try:
                return self.health.update("profile", {"name": name}, expected)
            except ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(client, (self.prefix + "-A", self.prefix + "-B")))
        self.assertEqual(sum(answer is not None for answer in answers), 1)
        stable = self.health.read()
        original_execute = psycopg.Connection.execute

        def fail_during_state_publish(connection, query, *args, **kwargs):
            if isinstance(query, str) and query.startswith("UPDATE personal_health_state SET"):
                raise RuntimeError("synthetic transaction failure after revision insertion")
            return original_execute(connection, query, *args, **kwargs)

        with patch.object(psycopg.Connection, "execute", fail_during_state_publish):
            with self.assertRaises(RuntimeError):
                self.health.save(
                    "checkins", {"id": self.prefix + "-rolled-back", "date": self.day.isoformat(), "fatigue": 4}
                )
        self.assertEqual(self.health.read(), stable)
        with repository.connect() as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT revision FROM operations.personal_health_revisions WHERE revision=%s",
                    (stable["revision"] + 1,),
                ).fetchone()
            )

    def test_food_artifacts_and_imports_roundtrip_and_transaction_abort(self):
        self.publish_synthetic()
        diary = FoodDiary(self.runtime, self.root)
        saved = diary.change(
            self.day, entry={"id": self.prefix + "-food", "text": "Synthetic pending meal", "analysis": None}
        )
        again = FoodDiary(self.runtime, self.root).read(self.day)
        self.assertEqual(again["revision"], saved["revision"])
        self.assertEqual(again["pending_count"], 1)
        self.assertTrue(any(entry["id"] == self.prefix + "-food" for entry in again["entries"]))
        artifacts = Artifacts(self.runtime, self.root)
        record = artifacts.save(
            self.prefix + "-planning",
            {"id": self.prefix + "-plan", "date": self.day.isoformat(), "title": "Synthetic plan"},
        )
        reread = Artifacts(self.runtime, self.root).read(self.prefix + "-planning")
        self.assertEqual(reread, [record])
        imports = ImportService(self.runtime, self.root)
        content = f"id,date,type,duration_seconds,distance_km\n{self.prefix},{self.day},Run,1800,5\n"
        first = imports.import_file("csv", self.prefix + ".csv", content)
        repeated = ImportService(self.runtime, self.root).import_file("csv", self.prefix + ".csv", content)
        self.assertTrue(repeated["repeated"])
        self.assertEqual(repeated["revision"], first["revision"])
        self.assertTrue(
            any(
                item["id"] == first["import"]["id"] for item in ImportService(self.runtime, self.root).read()["imports"]
            )
        )
        abort_key = self.prefix + "-abort"
        with self.assertRaises(RuntimeError):
            with repository.operational_db() as conn:
                repository.operational_lock(conn)
                conn.execute("INSERT INTO personal_artifacts(id,payload) VALUES(%s,%s)", (abort_key, Jsonb([])))
                raise RuntimeError("synthetic abort")
        with repository.operational_db() as conn:
            self.assertIsNone(
                conn.execute("SELECT payload FROM personal_artifacts WHERE id=%s", (abort_key,)).fetchone()
            )
        for name in ("health", "food", "artifacts", "imports"):
            self.assertFalse((self.runtime / (name + ".sqlite")).exists())


if __name__ == "__main__":
    unittest.main()
