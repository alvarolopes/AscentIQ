from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.repository as repository
from dashboard.jobs import JobManager, schedule_slot
from dashboard.pipeline import chart_svg, publish_report, sync_sources, training_snapshot
from dashboard.server import create_app
from dashboard.settings import Settings, default_tz
from dashboard.snapshot import activity_kind, build_snapshot, medical_documents, seconds
from dashboard.tests import pg


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.runtime = self.root / "runtime"

    def tearDown(self):
        self.temp.cleanup()

    def save(self, name, payload):
        (self.root / "data" / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


class SnapshotTests(Fixture):
    def test_legacy_height_is_available_without_inventing_metabolic_sex(self):
        self.save('athlete_profile', {'age': 43, 'height_m': 1.78})
        athlete = build_snapshot(self.root, date(2026, 9, 28))['athlete']
        self.assertEqual(athlete['height_cm'], 178)
        self.assertIsNone(athlete['sex'])
        self.save('athlete_profile', {'height_cm': 180, 'height_m': 1.78, 'sex': 'male'})
        athlete = build_snapshot(self.root, date(2026, 9, 28))['athlete']
        self.assertEqual(athlete['height_cm'], 180)
        self.assertEqual(athlete['sex'], 'male')

    def test_dark_web_chart_and_light_print_chart(self):
        rows = [{"date": "2026-09-28", "fitness": 54.4, "fatigue": 53.1, "form": 1.3}]
        self.assertIn('#0d1117', chart_svg(rows, dark=True))
        self.assertIn('#3fb950', chart_svg(rows, dark=True))
        self.assertIn('#fcfaf5', chart_svg(rows))
        self.assertNotIn('#0d1117', chart_svg(rows))

    def test_pdf_input_excludes_health_body_and_nutrition(self):
        snapshot = build_snapshot(self.root, date(2026, 9, 28))
        snapshot["medical"] = {"secret": "medical-marker"}
        snapshot["body"] = {"secret": "body-marker"}
        snapshot["physiology"] = [{"secret": "physiology-marker"}]
        snapshot["nutrition"] = {"secret": "nutrition-marker"}
        snapshot["performance"]["summary"]["recovery"] = {"secret": "sleep-marker"}
        result = training_snapshot(snapshot)
        for field in ("medical", "body", "physiology", "nutrition", "goals"):
            self.assertNotIn(field, result)
        self.assertNotIn("recovery", result["performance"]["summary"])
        for marker in ("medical-marker", "body-marker", "physiology-marker", "nutrition-marker", "sleep-marker"):
            self.assertNotIn(marker, json.dumps(result))
        self.assertIn("activities", result)
        self.assertIn("strength", result)

    def test_activity_types(self):
        for raw, kind in (
            ("Run", "running"),
            ("Corrida", "running"),
            ("Weight Training", "strength"),
            ("Natação", "swimming"),
            ("Ride", "cycling"),
        ):
            self.assertEqual(activity_kind({"type": raw}), kind)

    def test_duration(self):
        self.assertEqual(seconds("01:02:03"), 3723)
        self.assertEqual(seconds("invalid"), 0)

    def test_official_zero_overrides_watch(self):
        self.save(
            "training_history",
            [{"date": "2026-09-28", "type": "Run", "watch_elevation_gain_m": 40, "official_elevation_gain_m": 0}],
        )
        snapshot = build_snapshot(self.root, date(2026, 9, 28))
        self.assertEqual(snapshot["activities"][0]["elevation_gain_m"], 0)
        self.assertEqual(snapshot["activities"][0]["elevation_source"], "official")

    def test_missing_not_zero(self):
        self.save("strength_training_consolidated", [{"date": "2026-09-28"}])
        snapshot = build_snapshot(self.root, date(2026, 9, 28))
        self.assertIsNone(snapshot["strength"][0]["volume_kg"])
        self.assertIsNone(snapshot["strength"][0]["duration_seconds"])

    def test_strength_duration_is_available_for_daily_totals(self):
        self.save(
            "strength_training_consolidated",
            [
                {"date": "2026-09-28", "garmin_elapsed_time": "00:51:16", "hevy_duration": "00:50:00"},
                {"date": "2026-09-28", "hevy_workout_id": "h2", "hevy_duration": "01:05:00"},
            ],
        )
        rows = build_snapshot(self.root, date(2026, 9, 28))["strength"]
        self.assertEqual([row["duration_seconds"] for row in rows], [3076, 3900])

    def test_hevy_link_one_consolidated_session(self):
        self.save("hevy_workouts", [{"hevy_workout_id": "h1", "exercises": [{"name": "Squat"}]}])
        self.save(
            "strength_training_consolidated",
            [{"date": "2026-09-28", "hevy_workout_id": "h1", "garmin_match_status": "matched", "hevy_working_sets": 3}],
        )
        snapshot = build_snapshot(self.root, date(2026, 9, 28))
        self.assertEqual(snapshot["week"]["strength_sessions"], 1)
        self.assertEqual(snapshot["strength"][0]["exercises"][0]["name"], "Squat")

    def test_week_excludes_future_and_old(self):
        self.save(
            "training_history",
            [{"date": day, "type": "Run", "distance_km": 10} for day in ("2026-09-21", "2026-09-22", "2026-09-29")],
        )
        self.assertEqual(build_snapshot(self.root, date(2026, 9, 28))["week"]["running_km"], 10)

    def test_body_date_and_unknown_recovery(self):
        self.save("body_metrics", {"reference_date": "2026-07-21", "current": {"weight_kg": 91}})
        self.save("performance_management_model", {"summary": {"recovery": {"status": "unknown", "score": None}}})
        snapshot = build_snapshot(self.root, date(2026, 9, 28))
        self.assertEqual(snapshot["freshness"]["body"], "2026-07-21")
        self.assertIsNone(snapshot["performance"]["summary"]["recovery"]["score"])

    def test_document_path_traversal_blocked(self):
        (self.root / "secret.pdf").write_bytes(b"private")
        self.save(
            "medical_history", {"records": [{"date": "2026-09-19", "label": "Test", "source_file": "secret.pdf"}]}
        )
        self.assertEqual(medical_documents(self.root), {})
        snapshot = build_snapshot(self.root)
        self.assertNotIn("source_file", snapshot["medical"]["records"][0])


class JobsTests(Fixture):
    def test_reject_concurrent_and_invalid_mode(self):
        manager = JobManager(Settings.from_env(), self.runtime, self.root)
        manager.enqueue("generate")
        with self.assertRaises(RuntimeError):
            manager.enqueue("sync")
        with self.assertRaises(ValueError):
            manager.enqueue("bad")

    def test_interrupted_job_marked_failed(self):
        manager = JobManager(Settings.from_env(), self.runtime, self.root)
        key = manager.enqueue("generate")
        manager.update(key, "running", "Test")
        restored = JobManager(Settings.from_env(), self.runtime, self.root)
        self.assertEqual(restored.list()[0]["status"], "failed")

    def test_schedule_fuso_and_one_job(self):
        manager = JobManager(Settings.from_env(), self.runtime, self.root)
        future = schedule_slot(datetime.now(default_tz())) + timedelta(days=7, minutes=1)
        manager.tick_schedule(future)
        manager.tick_schedule(future)
        self.assertEqual(len(manager.list()), 1)
        self.assertEqual(manager.list()[0]["mode"], "sync")

    def test_monday_before_seven(self):
        self.assertEqual(schedule_slot(datetime(2026, 9, 28, 6, 59, tzinfo=default_tz())).date(), date(2026, 9, 21))
        self.assertEqual(schedule_slot(datetime(2026, 9, 28, 7, 0, tzinfo=default_tz())).date(), date(2026, 9, 28))

    def test_failed_compile_preserves_previous(self):
        (self.root / "dashboard" / "templates").mkdir(parents=True)
        (self.root / "dashboard" / "templates" / "weekly.typ").write_text("test")
        (self.root / "dashboard" / "templates" / "dashboard-html.typ").write_text("test")
        (self.root / "dashboard" / "templates" / "report.css").write_text("test")
        self.runtime.mkdir()
        (self.runtime / "latest.json").write_text('{"id":"previous"}')
        snapshot = build_snapshot(self.root)
        with patch("dashboard.pipeline.subprocess.run", side_effect=RuntimeError("compile failed")):
            with self.assertRaises(RuntimeError):
                publish_report(snapshot, "failed-job", self.runtime, self.root)
        self.assertEqual(json.loads((self.runtime / "latest.json").read_text())["id"], "previous")

    def test_missing_credentials_no_remote_call(self):
        with patch("dashboard.pipeline.run_script") as run:
            with self.assertRaises(RuntimeError):
                sync_sources(self.root, credentials={}, enabled={})
            run.assert_not_called()


class ApiTests(Fixture):
    def setUp(self):
        super().setUp()
        self.app = create_app(
            self.runtime,
            self.root,
            Settings.from_env(
                {**os.environ, "DASHBOARD_PASSWORD": "test-only-password", "DASHBOARD_USERNAME": "alvaro"}
            ),
        )
        self.client = TestClient(self.app)

    def login(self):
        return self.client.post(
            "/api/auth/login",
            json={"username": "alvaro", "password": "test-only-password"},
            headers={"X-AscentIQ-Request": "1"},
        )

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_private_routes_require_auth(self):
        for path in (
            "/api/dashboard",
            "/api/jobs",
            "/api/reports",
            "/api/reports/example/pdf",
            "/api/reports/example/html",
            "/api/medical/documents/missing",
        ):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

    def test_only_training_pdfs_are_listed_and_downloadable(self):
        for key, meta in (
            ("old-report", {"id": "old-report"}),
            ("training-report", {"id": "training-report", "pdf_scope": "training"}),
        ):
            folder = self.runtime / "reports" / key
            folder.mkdir(parents=True)
            (folder / "meta.json").write_text(json.dumps(meta))
            (folder / "report.pdf").write_bytes(b"%PDF-1.7 test")
            from psycopg.types.json import Jsonb

            with repository.connect() as conn:
                conn.execute(
                    "INSERT INTO athlete.reports(id, metadata) VALUES(%s, %s)",
                    (key, Jsonb(meta)),
                )
        self.login()
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/reports").json()["reports"]], ["training-report"]
        )
        self.assertEqual(self.client.get("/api/reports/old-report/pdf").status_code, 404)
        response = self.client.get("/api/reports/training-report/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.headers["content-type"], "application/pdf")

    def test_cookie_and_no_store(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/dashboard").headers["cache-control"], "no-store")

    def test_logout_revokes(self):
        self.login()
        response = self.client.post("/api/auth/logout", json={}, headers={"X-AscentIQ-Request": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)

    def test_csrf_and_cross_origin(self):
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "a", "password": "b"},
                headers={"X-AscentIQ-Request": "1", "Origin": "https://evil.invalid"},
            ).status_code,
            403,
        )

    def test_invalid_credentials_and_mode(self):
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"username": "a", "password": "b"}, headers={"X-AscentIQ-Request": "1"}
            ).status_code,
            401,
        )
        self.login()
        self.assertEqual(
            self.client.post("/api/jobs", json={"mode": "invalid"}, headers={"X-AscentIQ-Request": "1"}).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
