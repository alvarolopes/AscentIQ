"""Synthetic fixtures only. Database tests require a disposable database."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard.repository as repository_module
from dashboard.backup import create_backup, verify
from dashboard.repository import (
    CURRENT,
    FILES_CACHE,
    ROOT,
    PostgresRepository,
    connect,
    contents_digest,
    identity,
    operational_db,
    operational_lock,
    read_dataset,
    validate_path,
)
from dashboard.settings import Settings
from dashboard.tests import pg


class LocalRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def test_completed_job_cannot_be_processed_twice(self):
        from dashboard.jobs import JobManager

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manager = JobManager(Settings.from_env(), root / "runtime", root)
            manager.enqueue("generate")
            job = manager.list()[0]
            with patch("dashboard.database_pipeline.run_database_pipeline", return_value=[]) as rebuild:
                manager.process(job)
                manager.process(job)
            rebuild.assert_called_once()
            self.assertEqual(manager.list()[0]["status"], "completed")

    def test_failed_provider_restores_sleep_and_activities(self):
        from dashboard.pipeline import sync_sources

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "data").mkdir()
            files = {"training_history": b'[]', "sleep_reference": b'{"score":null}'}
            for key, raw in files.items():
                (root / "data" / (key + ".json")).write_bytes(raw)

            def fail(*args, **kwargs):
                for key in files:
                    (root / "data" / (key + ".json")).write_bytes(b'[]')
                raise RuntimeError("synthetic source failure")

            with patch("dashboard.pipeline.run_script", side_effect=fail):
                self.assertTrue(
                    sync_sources(
                        root,
                        sources=("garmin",),
                        credentials={"garmin": {"email": "synthetic", "password": "synthetic"}},
                        enabled={"garmin": True},
                    )
                )
            for key, raw in files.items():
                self.assertEqual((root / "data" / (key + ".json")).read_bytes(), raw)

    def test_path_traversal(self):
        for value in ("../secret.json", "/data/x.json", "runtime/auth.json", "data/x.pdf"):
            with self.assertRaises(ValueError):
                validate_path(value)

    def test_context_preserves_null_and_official_zero(self):
        token = CURRENT.set({"data/example.json": b'{"avg_hr":null,"official_elevation_gain_m":0}'})
        try:
            self.assertEqual(read_dataset(ROOT, "data/example.json"), {"avg_hr": None, "official_elevation_gain_m": 0})
        finally:
            CURRENT.reset(token)

    def test_provider_identity_survives_title_change(self):
        self.assertEqual(
            identity({"garmin_activity_id": "test-id", "name": "old"}),
            identity({"garmin_activity_id": "test-id", "name": "new"}),
        )

    def test_digest_checks_every_original_byte(self):
        self.assertNotEqual(
            contents_digest({"data/a.json": b'{"x":1}'}), contents_digest({"data/a.json": b'{ "x":1 }'})
        )

    def test_encrypted_backup_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "synthetic.json").write_text('{"marker":"synthetic-private-data"}')
            output = root / "runtime" / "backups"
            result = create_backup(root, output)
            archive = output / result["archive"]
            self.assertNotIn(b"synthetic-private-data", archive.read_bytes())
            self.assertTrue(verify(archive, output / "recovery.key")["verified"])
            corrupt = bytearray(archive.read_bytes())
            corrupt[-20] ^= 1
            archive.write_bytes(corrupt)
            with self.assertRaises(Exception):  # noqa: B017 - InvalidTag da cryptography, não RuntimeError
                verify(archive, output / "recovery.key")


class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def fixture(self, label):
        return {
            "data/training_history.json": json.dumps(
                [
                    {
                        "garmin_activity_id": label,
                        "date": "2020-01-01",
                        "name": label,
                        "type": "Run",
                        "avg_hr": None,
                        "official_elevation_gain_m": 0,
                    }
                ]
            ).encode(),
            "data/hevy_workouts.json": b'[]',
            "data/strength_training_consolidated.json": b'[]',
        }

    def test_round_trip_idempotence_and_nulls(self):
        repo = PostgresRepository()
        files = self.fixture("round-trip")
        revision = repo.publish(files, reason="synthetic", expected=repo.active())
        again = repo.publish(files, reason="synthetic", expected=revision)
        self.assertEqual(revision, again)
        self.assertEqual(repo.files()[1], files)
        self.assertEqual(repo.counts()["activities"], 1)
        with connect() as conn:
            row = conn.execute(
                "SELECT avg_hr,official_gain_m FROM athlete.activities WHERE revision_id=%s", (revision,)
            ).fetchone()
            self.assertEqual(row, (None, 0.0))
        with tempfile.TemporaryDirectory() as name:
            repo.export(Path(name))
            self.assertEqual(
                (Path(name) / "data/training_history.json").read_bytes(), files["data/training_history.json"]
            )

    def test_conflicting_writer_does_not_overwrite(self):
        repo = PostgresRepository()
        initial = repo.active()
        revision = repo.publish(self.fixture("newer"), reason="synthetic", expected=initial)
        with self.assertRaises(RuntimeError):
            repo.publish(self.fixture("stale"), reason="synthetic", expected=initial)
        self.assertEqual(repo.active(), revision)

    def test_failed_projection_rolls_back(self):
        repo = PostgresRepository()
        initial = repo.active()
        with patch.object(repo, "_project", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                repo.publish(self.fixture("failed"), reason="synthetic", expected=initial)
        self.assertEqual(repo.active(), initial)

    def test_duplicate_provider_ids_require_review(self):
        repo = PostgresRepository()
        initial = repo.active()
        files = self.fixture("duplicate")
        row = json.loads(files["data/training_history.json"])[0]
        files["data/training_history.json"] = json.dumps([row, row]).encode()
        with self.assertRaises(Exception):  # noqa: B017 - psycopg.errors.UniqueViolation no Postgres
            repo.publish(files, reason="synthetic", expected=initial)
        self.assertEqual(repo.active(), initial)

    def test_operational_queue_uses_postgres(self):
        with operational_db() as conn:
            operational_lock(conn)
            conn.execute("INSERT INTO settings VALUES (%s, %s) ON CONFLICT DO NOTHING", ("test-setting", "1"))
            self.assertEqual(
                conn.execute("SELECT value FROM settings WHERE key=%s", ("test-setting",)).fetchone()[0], "1"
            )

    def test_strength_sets_and_provider_link_preserved(self):
        repo = PostgresRepository()
        files = self.fixture("strength-garmin")
        workout = {
            "hevy_workout_id": "strength-hevy",
            "exercises": [
                {
                    "name": "Synthetic squat",
                    "sets": [
                        {"set_type": "warmup", "weight_kg": 10, "reps": 5, "rpe": None},
                        {"set_type": "normal", "weight_kg": 20, "reps": 8, "rpe": 6},
                    ],
                }
            ],
        }
        files["data/hevy_workouts.json"] = json.dumps([workout]).encode()
        files["data/strength_training_consolidated.json"] = json.dumps(
            [
                {
                    "date": "2020-01-01",
                    "garmin_activity_id": "strength-garmin",
                    "hevy_workout_id": "strength-hevy",
                    "garmin_match_status": "matched",
                    "hevy_total_volume_kg": 210,
                }
            ]
        ).encode()
        revision = repo.publish(files, reason="synthetic", expected=repo.active())
        self.assertEqual(repo.counts()["strength_sessions"], 1)
        self.assertEqual(repo.counts()["exercise_sets"], 2)
        with connect() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT count(DISTINCT activity_id) FROM athlete.activity_sources WHERE revision_id=%s", (revision,)
                ).fetchone()[0],
                1,
            )

    def test_publish_invalidates_files_cache(self):
        class Recording:
            def __init__(self, conn, queries):
                self.conn = conn
                self.queries = queries

            def __enter__(self):
                self.conn.__enter__()
                return self

            def __exit__(self, *args):
                return self.conn.__exit__(*args)

            def execute(self, query, values=None):
                self.queries.append(query)
                return self.conn.execute(query) if values is None else self.conn.execute(query, values)

        repo = PostgresRepository()
        FILES_CACHE.invalidate()
        first = repo.publish(self.fixture("cache-v1"), reason="synthetic", expected=repo.active())
        queries: list = []
        real_connect = repository_module.connect
        with patch.object(
            repository_module, "connect", side_effect=lambda **kwargs: Recording(real_connect(**kwargs), queries)
        ):
            self.assertEqual(repo.files()[0], first)
            repo.files()
        self.assertEqual(len([q for q in queries if "dataset_blobs" in q]), 1)
        second = repo.publish(self.fixture("cache-v2"), reason="synthetic", expected=first)
        self.assertEqual(repo.files()[0], second)
        self.assertEqual(json.loads(repo.files()[1]["data/training_history.json"])[0]["name"], "cache-v2")
        FILES_CACHE.invalidate()

    def test_postgres_auth_and_job_exclusion(self):
        from fastapi.testclient import TestClient

        from dashboard.jobs import JobManager
        from dashboard.server import create_app

        with tempfile.TemporaryDirectory() as name:
            runtime = Path(name)
            client = TestClient(
                create_app(
                    runtime,
                    Path(name),
                    Settings.from_env(
                        {**os.environ, "DASHBOARD_PASSWORD": "synthetic-test", "DASHBOARD_USERNAME": "athlete"}
                    ),
                )
            )
            self.assertEqual(client.get("/api/dashboard").status_code, 401)
            response = client.post(
                "/api/auth/login",
                json={"username": "athlete", "password": "synthetic-test"},
                headers={"X-AscentIQ-Request": "1"},
            )
            self.assertEqual(response.status_code, 200)
            manager = JobManager(Settings.from_env(), runtime, recover_interrupted=False)
            manager.enqueue("generate")
            with self.assertRaises(RuntimeError):
                manager.enqueue("sync")
            client.close()


if __name__ == "__main__":
    unittest.main()
