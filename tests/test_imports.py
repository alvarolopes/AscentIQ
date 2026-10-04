from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dashboard.imports import ImportService
from dashboard.repository import operational_db
from scripts.fetch_garmin_mcp_snapshot import extract_activity_ids, fetch_all_activities, filter_known_activities
from scripts.import_garmin_mcp_snapshot import extract_activities, extract_daily_energy, merge_daily_energy, merge_history, normalize_activity


CSV = "id,date,type,duration_seconds,name,distance_km,elevation_gain_m,avg_hr,calories\na,2026-10-01T08:00:00-03:00,Run,1800,Easy run,5,20,135,450\n"
GPX = '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Planned route</name><trkseg><trkpt lat="-23.0" lon="-46.0"><ele>100</ele><time>2026-10-01T08:00:00Z</time></trkpt><trkpt lat="-23.001" lon="-46.001"><ele>110</ele><time>2026-10-01T08:30:00Z</time></trkpt></trkseg></trk></gpx>'


def synthetic_fit():
    """A real minimal FIT session with CRC, using only synthetic observations."""
    from fitdecode.utils import compute_crc
    fields = [(2, 4, 0x86), (5, 1, 0), (7, 4, 0x86), (8, 4, 0x86), (9, 4, 0x86),
              (11, 2, 0x84), (16, 1, 2), (17, 1, 2), (22, 2, 0x84)]
    definition = bytes([0x40, 0, 0]) + struct.pack("<H", 18) + bytes([len(fields)])
    definition += b"".join(bytes(field) for field in fields)
    epoch = datetime(1989, 12, 31, tzinfo=timezone.utc)
    start = int((datetime(2026, 10, 1, 11, tzinfo=timezone.utc) - epoch).total_seconds())
    message = b"\x00" + struct.pack("<IBIIIHBBH", start, 1, 1800000, 1700000, 500000, 450, 135, 160, 20)
    payload = definition + message
    header = bytes([12, 0x20]) + struct.pack("<HI", 100, len(payload)) + b".FIT"
    original = header + payload
    return original + struct.pack("<H", compute_crc(original))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.service = ImportService(self.runtime, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_repeated_csv_is_one_receipt_record_and_original(self):
        first = self.service.import_file("csv", "first.csv", CSV)
        second = ImportService(self.runtime, self.root).import_file("csv", "renamed.csv", CSV)
        self.assertFalse(first["repeated"])
        self.assertTrue(second["repeated"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(len(second["imports"]), 1)
        self.assertEqual(len(second["records"]), 1)
        self.assertEqual(len(list(self.service.originals.glob("*.csv"))), 1)
        self.assertEqual(second["records"][0]["date_time"], "2026-10-01T08:00:00-03:00")

    def test_correction_preserves_missing_calories_and_supports_real_zero(self):
        first = self.service.import_file("csv", "a.csv", CSV)
        corrected = CSV.replace("Easy run,5,20,135,450", ",5,0,140,null")
        second = self.service.import_file("csv", "corrected.csv", corrected)
        row = second["records"][0]
        self.assertEqual(row["id"], first["records"][0]["id"])
        self.assertEqual(row["calories"], 450)
        self.assertEqual(row["elevation_gain_m"], 0)
        self.assertEqual(row["avg_hr"], 140)
        self.assertEqual(row["name"], "Easy run")
        self.assertEqual(len(row["sources"]), 2)
        self.assertEqual(row["field_observation_sources"]["calories"]["import_id"], first["import"]["id"])
        self.assertEqual(row["field_observation_sources"]["avg_hr"]["import_id"], second["import"]["id"])
        self.assertEqual(second["revision"], 2)
        with operational_db(self.runtime, "imports", self.root) as conn:
            count = conn.execute("SELECT count(*) FROM personal_imports_state WHERE id != ?", ("state",)).fetchone()[0]
        self.assertEqual(count, 2)

    def test_missing_optional_numeric_values_are_unknown(self):
        result = self.service.import_file("csv", "small.csv", "id,date,type,duration_seconds\na,2026-10-01,Walk,600\n")
        row = result["records"][0]
        self.assertIsNone(row.get("calories"))
        self.assertIsNone(row.get("distance_km"))
        self.assertEqual(row["name"], "Walk")

    def test_optional_separate_date_time_preserves_manual_event_offset(self):
        result = self.service.import_file("csv", "manual.csv", "id,date,date_time,type,duration_seconds\na,2026-10-01,2026-10-01T08:00:00-03:00,Run,1800\n")
        self.assertEqual(result["records"][0]["date_time"], "2026-10-01T08:00:00-03:00")
        with self.assertRaises(ValueError):
            self.service.import_file("csv", "badtime.csv", "id,date,date_time,type,duration_seconds\nb,2026-10-01,2026-10-02T08:00:00-03:00,Run,1800\n")

    def test_invalid_values_are_atomic_and_do_not_save_originals(self):
        for invalid in (CSV.replace(",450", ",NaN"), CSV.replace("1800", "-20"), CSV + CSV.splitlines()[1] + "\n"):
            with self.assertRaises(ValueError):
                self.service.import_file("csv", "invalid.csv", invalid)
        self.assertEqual(self.service.read()["revision"], 0)
        self.assertEqual(list(self.service.originals.iterdir()), [])

    def test_filename_paths_cannot_access_or_escape_workspace(self):
        for filename in ("../outside.csv", "..\\outside.csv", "C:\\outside.csv", "/tmp/out.csv", "x.csv:stream"):
            with self.assertRaises(ValueError):
                self.service.import_file("csv", filename, CSV)
        self.assertEqual(list(self.service.originals.iterdir()), [])

    def test_gpx_is_route_even_when_points_have_times(self):
        result = self.service.import_file("gpx", "route.gpx", GPX)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["routes"][0]["point_count"], 2)
        self.assertFalse(result["routes"][0]["execution_evidence"])
        self.assertEqual(result["routes"][0]["elevation_gain_m"], 10)
        overlay = self.service.overlay({"activities": [], "week": {"start": "2026-09-25", "end": "2026-10-01"}})
        self.assertEqual(overlay["week"]["activity_count"], 0)

    def test_gpx_does_not_bridge_disconnected_segments_and_rejects_entities(self):
        distant = '<gpx><trk><trkseg><trkpt lat="0" lon="0"/></trkseg><trkseg><trkpt lat="40" lon="40"/></trkseg></trk></gpx>'
        result = self.service.import_file("gpx", "segments.gpx", distant)
        self.assertEqual(result["routes"][0]["distance_km"], 0)
        unsafe = '<!DOCTYPE gpx [<!ENTITY x SYSTEM "file:///secret">]><gpx>&x;</gpx>'
        with self.assertRaises(ValueError):
            self.service.import_file("gpx", "unsafe.gpx", unsafe)

    def test_fit_summary_is_parsed_with_real_binary_fixture(self):
        result = self.service.import_file("fit", "session.fit", base64.b64encode(synthetic_fit()).decode())
        row = result["records"][0]
        self.assertEqual(row["duration_seconds"], 1800)
        self.assertEqual(row["moving_time_seconds"], 1700)
        self.assertEqual(row["distance_km"], 5)
        self.assertEqual(row["calories"], 450)
        self.assertEqual(row["avg_hr"], 135)
        self.assertTrue(row["date_time"].endswith("+00:00"))
        bad = bytearray(synthetic_fit())
        bad[-1] ^= 1
        with self.assertRaises(ValueError):
            self.service.import_file("fit", "broken.fit", base64.b64encode(bad).decode())
        with self.assertRaises(ValueError):
            self.service.import_file("fit", "notbase64.fit", "../session.fit")

    def test_ambiguous_activities_remain_separate_until_merge_and_can_unlink(self):
        first = self.service.import_file("csv", "a.csv", CSV)
        another = CSV.replace("\na,", "\nb,").replace("1800", "1850").replace(",135,450", ",140,460")
        second = self.service.import_file("csv", "b.csv", another)
        self.assertEqual(len(second["records"]), 2)
        self.assertEqual(len(second["reconciliation"]), 1)
        a, b = first["records"][0]["id"], next(row["id"] for row in second["records"] if row["id"] != first["records"][0]["id"])
        merged = self.service.reconcile(a, "merge", b)
        self.assertEqual(len(merged["records"]), 1)
        self.assertEqual(merged["records"][0]["duration_seconds"], 1800)
        self.assertEqual(merged["records"][0]["calories"], 450)
        self.assertIn("duration_seconds", merged["records"][0]["conflicts"])
        self.assertEqual(len(merged["records"][0]["sources"]), 2)
        repeat = self.service.reconcile(a, "merge", b)
        self.assertEqual(repeat["revision"], merged["revision"])
        restored = self.service.reconcile(a, "unlink", b)
        self.assertEqual(len(restored["records"]), 2)
        self.assertEqual({row["calories"] for row in restored["records"]}, {450, 460})

    def test_legacy_link_suppresses_one_baseline_without_rewriting_it(self):
        data = self.root / "data"
        data.mkdir()
        original = json.dumps([{"garmin_activity_id": "123", "date": "2026-10-01", "date_time": "2026-10-01T08:00:00-03:00", "type": "Run", "name": "Watch run", "duration_seconds": 1800, "avg_hr": 130, "distance_km": 5}])
        history = data / "training_history.json"
        history.write_text(original)
        result = self.service.import_file("csv", "a.csv", CSV)
        a = result["records"][0]["id"]
        merged = self.service.reconcile("legacy:123", "merge", a)
        self.assertEqual(merged["suppressed_legacy_ids"], ["123"])
        snapshot = {"activities": [{"id": "123", "date": "2026-10-01", "type": "Run", "kind": "running", "duration_seconds": 1800, "distance_km": 5, "hevy_workout_id": "keep-me"}],
                    "source_digest": "baseline", "week": {"start": "2026-09-25", "end": "2026-10-01"}}
        overlay = self.service.overlay(snapshot)
        self.assertEqual(len(overlay["activities"]), 1)
        self.assertEqual(overlay["activities"][0]["calories"], 450)
        self.assertEqual(overlay["activities"][0]["avg_hr"], 130)
        self.assertEqual(overlay["activities"][0]["hevy_workout_id"], "keep-me")
        self.assertEqual(overlay["week"]["minutes"], 30)
        self.assertEqual(snapshot["activities"][0]["id"], "123")
        self.assertEqual(history.read_text(), original)
        self.service.reconcile("legacy:123", "unlink", a)
        self.assertEqual(len(self.service.overlay(snapshot)["activities"]), 2)

    def test_keep_separate_remembers_review_and_does_not_hide_records(self):
        first = self.service.import_file("csv", "a.csv", CSV)
        second = self.service.import_file("csv", "b.csv", CSV.replace("\na,", "\nb,"))
        a = first["records"][0]["id"]
        b = next(row["id"] for row in second["records"] if row["id"] != a)
        kept = self.service.reconcile(a, "keep", b)
        self.assertEqual(len(kept["records"]), 2)
        self.assertEqual(kept["reconciliation"], [])
        self.assertEqual(self.service.reconcile(a, "keep", b)["revision"], kept["revision"])
        merged = self.service.reconcile(a, "merge", b)
        self.assertEqual(len(merged["records"]), 1)
        self.assertEqual(merged["distinct_pairs"], [])

    def test_concurrent_imports_do_not_lose_each_other(self):
        def save(index):
            return self.service.import_file("csv", f"{index}.csv", CSV.replace("\na,", f"\n{index},"))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(8)))
        view = ImportService(self.runtime, self.root).read()
        self.assertEqual((len(view["imports"]), len(view["records"]), view["revision"]), (8, 8, 8))


class GarminImportTests(unittest.TestCase):
    def test_observation_order_wins_over_snapshot_filename_order(self):
        new = {"generated_at": "2026-10-02T12:00:00-03:00", "daily_summary": {"date": "2026-10-01", "isComplete": True, "userSummary": {"totalKilocalories": 2800}},
               "activities": [{"activityId": 1, "startTimeLocal": "2026-10-01T08:00:00", "activityName": "Corrected", "activityType": "running", "duration": 1900}]}
        old = {"generated_at": "2026-10-01T12:00:00-03:00", "daily_summary": {"date": "2026-10-01", "totalKilocalories": 2500},
               "activities": [{"activityId": 1, "startTimeLocal": "2026-10-01T08:00:00", "activityName": "Old", "activityType": "running", "duration": 1800}]}
        daily = extract_daily_energy([new, old])[0]
        self.assertEqual((daily["total_kcal"], daily["coverage"]), (2800, "complete"))
        activity = extract_activities([new, old])[0]
        self.assertEqual((activity["name"], activity["duration_seconds"]), ("Corrected", 1900))

    def test_daily_total_stays_separate_from_active_and_exercise(self):
        payload = {"generated_at": "2026-10-02T12:00:00-03:00", "daily_metrics": {"get_daily_summary": [{"date": "2026-10-01", "payload": {"totalKilocalories": 2800, "activeKilocalories": 800, "bmrKilocalories": 2000, "isComplete": True,
                   "activities": [{"activityId": 3, "totalCalories": 500}]}}]},
                   "activities": [{"calendarDate": "2026-10-01", "totalCalories": 500}]}
        row = extract_daily_energy([payload])[0]
        self.assertEqual((row["total_kcal"], row["active_kcal"], row["resting_kcal"]), (2800, 800, 2000))
        self.assertEqual(row["coverage"], "complete")
        self.assertTrue(row["total_includes_exercise"])

    def test_daily_merge_preserves_absent_days_values_and_real_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily_energy.json"
            path.write_text(json.dumps({"daily": [{"date": "2026-09-30", "total_kcal": 2500}, {"date": "2026-10-01", "total_kcal": 2800, "active_kcal": 800, "coverage": "complete"}]}))
            incoming = extract_daily_energy([{"daily_summary": [{"date": "2026-10-01", "totalKilocalories": None, "activeKilocalories": 0}]}])
            merged = merge_daily_energy(path, incoming)
            self.assertEqual(len(merged["daily"]), 2)
            current = merged["daily"][1]
            self.assertEqual((current["total_kcal"], current["active_kcal"], current["coverage"]), (2800, 0, "complete"))
            self.assertEqual(current["record_revision"], 2)
            self.assertEqual(current["revisions"][0]["active_kcal"], 800)

    def test_coverage_is_not_invented_and_invalid_numbers_are_ignored(self):
        rows = extract_daily_energy([{"daily_summary": [{"date": "2026-10-01", "totalKilocalories": 2800}, {"date": "2026-10-02", "totalKilocalories": float("nan"), "activeKilocalories": None}]}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["coverage"], "unknown")
        self.assertEqual(extract_daily_energy([{"daily_metrics": {"get_daily_summary": [{"date": "2026-10-02", "payload": {"error": "not authenticated"}}]}}]), [])

    def test_existing_garmin_id_is_corrected_without_null_overwrite(self):
        previous = {"garmin_activity_id": "123", "date": "2026-10-01", "date_time": "2026-10-01T08:00:00", "type": "Run", "name": "Old", "duration_seconds": 1800, "distance_km": 5, "watch_elevation_gain_m": 20, "avg_hr": 130, "calories": 400, "source": "garmin"}
        new = normalize_activity({"activityId": 123, "startTimeLocal": "2026-10-01T08:00:00", "activityName": "Corrected", "activityType": {"typeKey": "running"}, "duration": 1900, "averageHR": 140, "calories": None})
        merged, added = merge_history([previous], [new], None)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, [])
        self.assertEqual((merged[0]["name"], merged[0]["duration_seconds"], merged[0]["avg_hr"]), ("Corrected", 1900, 140))
        self.assertEqual((merged[0]["distance_km"], merged[0]["watch_elevation_gain_m"], merged[0]["calories"]), (5, 20, 400))

    def test_distinct_garmin_ids_are_not_merged_by_similar_signature(self):
        first = {"garmin_activity_id": "1", "date_time": "2026-10-01T08:00:00", "date": "2026-10-01", "type": "Run", "name": "A", "duration_seconds": 1800, "distance_km": 5}
        second = {**first, "garmin_activity_id": "2", "name": "B"}
        result, _ = merge_history([first], [second], None)
        self.assertEqual(len(result), 2)

    def test_overlap_revisits_known_details_without_older_history(self):
        rows = [{"activityId": 3, "startTimeLocal": "2026-10-02T08:00:00"}, {"activityId": 2, "startTimeLocal": "2026-09-29T08:00:00"}, {"activityId": 1, "startTimeLocal": "2026-09-20T08:00:00"}]

        class Session:
            def __init__(self):
                self.calls = []

            async def call_tool(self, name, arguments):
                self.calls.append(arguments)
                return {"content": [{"text": json.dumps(rows[arguments["start"]:arguments["start"] + 2])}]}

        session = Session()
        result = asyncio.run(fetch_all_activities(session, SimpleNamespace(max_activities=50, activity_page_size=2), date(2026, 9, 25), date(2026, 10, 2), {1, 2, 3}, refresh_known_in_window=True))
        self.assertEqual(extract_activity_ids(result), [3, 2])
        self.assertEqual(result["known_items_refreshed"], 2)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(extract_activity_ids(filter_known_activities(rows, {1, 2, 3}, date(2026, 9, 25), date(2026, 10, 2))), [3, 2])


@unittest.skipUnless(os.environ.get("DATABASE_TEST_ENABLED") == "1", "Disposable PostgreSQL not configured")
class PostgresImportTests(unittest.TestCase):
    def test_operational_imports_and_reconciliation_use_postgres(self):
        from dashboard.repository import ROOT, migrate
        import uuid
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"DATABASE_BACKEND": "postgres"}), patch("dashboard.imports.read_dataset", return_value=[]):
            migrate()
            runtime = Path(temp)
            service = ImportService(runtime, ROOT)
            identifier = uuid.uuid4().hex
            original = CSV.replace("\na,", f"\n{identifier}-a,")
            first = service.import_file("csv", "a.csv", original)
            a = first["import"]["record_ids"][0]
            repeated = service.import_file("csv", "renamed.csv", original)
            self.assertTrue(repeated["repeated"])
            self.assertEqual(repeated["revision"], first["revision"])
            second = service.import_file("csv", "b.csv", CSV.replace("\na,", f"\n{identifier}-b,"))
            b = second["import"]["record_ids"][0]
            merged = service.reconcile(a, "merge", b)
            selected = next(row for row in merged["records"] if a in row["linked_record_ids"])
            self.assertEqual(set(selected["linked_record_ids"]), {a, b})
            self.assertEqual(selected["calories"], 450)
            self.assertFalse((runtime / "imports.sqlite").exists())
            with operational_db(runtime, "imports", ROOT) as conn:
                record = conn.execute("SELECT payload FROM personal_imports_state WHERE id=?", ("state",)).fetchone()
                self.assertEqual(json.loads(record[0])["revision"], merged["revision"])
            restored = service.reconcile(a, "unlink", b)
            self.assertTrue(any(row["id"] == b for row in restored["records"]))


if __name__ == "__main__":
    unittest.main()
