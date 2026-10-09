from __future__ import annotations

import unittest

from scripts.import_hevy_workouts import deduplicate_legacy_strength, match_sessions


class StrengthConsolidationTests(unittest.TestCase):
    def test_legacy_date_only_duplicate_prefers_timed_garmin(self):
        history: list[dict] = [
            {"date": "2026-02-25", "type": "Weight Training", "date_time": None, "elapsed_time": "00:47:55", "avg_hr": 110, "source": "strava_export", "relative_effort": 10},
            {"date": "2026-02-25", "type": "Weight Training", "date_time": "2026-02-25T08:12:54", "elapsed_time": "00:47:55", "avg_hr": 110, "source": "garmin_mcp_snapshot", "garmin_activity_id": "g1"},
        ]
        self.assertEqual(deduplicate_legacy_strength(history), 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["relative_effort"], 10)
        self.assertIn("strava_export", history[0]["source"])

    def test_one_daily_session_with_distinct_garmin_sources(self):
        sessions = [{"date": "2026-04-06", "start_time": "2026-04-06T11:31", "end_time": "2026-04-06T12:20", "hevy_workout_id": "h1", "title": "Pernas", "classification": "legs", "source": "hevy_api", "duration": "00:49:00", "exercise_count": 3, "total_sets": 9, "working_sets": 9, "total_reps": 90, "total_volume_kg": 1200, "exercises_preview": []}]
        history: list[dict] = [
            {"date": "2026-04-06", "type": "Weight Training", "date_time": "2026-04-06T11:31:46", "garmin_activity_id": "g1", "elapsed_time": "00:51:57", "avg_hr": 107, "max_hr": 140},
            {"date": "2026-04-06", "type": "Weight Training", "date_time": "2026-04-06T17:28:41", "garmin_activity_id": "g2", "elapsed_time": "00:23:02", "avg_hr": 131, "max_hr": 160},
        ]
        consolidated, links = match_sessions(sessions, history, 180)
        self.assertEqual(len(consolidated), 1)
        row = consolidated[0]
        self.assertEqual(row["garmin_activity_ids"], ["g1", "g2"])
        self.assertEqual(row["garmin_elapsed_time"], "01:14:59")
        self.assertEqual(row["garmin_max_hr"], 160)
        self.assertEqual(row["hevy_total_volume_kg"], 1200)
        self.assertEqual(len(links), 1)

    def test_two_hevy_sessions_same_day_keep_both_sources(self):
        sessions = [{"date": "2026-09-30", "start_time": f"2026-09-30T{hour}:00", "end_time": f"2026-09-30T{hour}:30", "hevy_workout_id": key, "title": "Força", "classification": "strength", "source": "hevy_api", "duration": "00:30:00", "exercise_count": 1, "total_sets": 3, "working_sets": 3, "total_reps": 30, "total_volume_kg": 300, "exercises_preview": []} for hour, key in (("08", "h1"), ("18", "h2"))]
        consolidated, _ = match_sessions(sessions, [], 180)
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(consolidated[0]["hevy_workout_ids"], ["h1", "h2"])
        self.assertEqual(consolidated[0]["hevy_total_volume_kg"], 600)


if __name__ == "__main__":
    unittest.main()
