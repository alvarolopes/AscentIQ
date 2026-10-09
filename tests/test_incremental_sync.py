from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from scripts.build_performance_management_model import build_recovery_summary
from scripts.compute_garmin_sync_window import sync_start
from scripts.fetch_garmin_mcp_snapshot import extract_activity_ids, fetch_all_activities, filter_known_activities
from scripts.fetch_hevy_workouts import HevyClient


class IncrementalSyncTests(unittest.TestCase):
    def test_garmin_window_uses_latest_garmin_date_not_hevy_date(self) -> None:
        history = [
            {"date": "2026-09-19", "garmin_activity_id": "123"},
            {"date": "2026-09-22", "source": "hevy_api"},
        ]
        self.assertEqual(
            sync_start(history, date(2026, 9, 23), date(2024, 1, 1), 7),
            date(2026, 9, 12),
        )

    def test_garmin_window_falls_back_for_empty_history(self) -> None:
        self.assertEqual(sync_start([], date(2026, 9, 23), date(2024, 1, 1), 7), date(2024, 1, 1))

    def test_garmin_details_include_only_unknown_activity_ids(self) -> None:
        listing = [{"activityId": 1}, {"activityId": 2}]
        filtered = filter_known_activities(listing, {1})
        self.assertEqual(extract_activity_ids(filtered), [2])

    def test_garmin_pagination_skips_known_and_stops_at_window(self) -> None:
        pages = [
            [
                {"activityId": 3, "startTimeLocal": "2026-09-23 09:00:00"},
                {"activityId": 2, "startTimeLocal": "2026-09-20 09:00:00"},
            ],
            [{"activityId": 1, "startTimeLocal": "2026-09-10 09:00:00"}],
        ]

        class FakeSession:
            async def call_tool(self, name, arguments):
                return {"content": [{"text": __import__("json").dumps(pages[arguments["start"] // 2])}]}

        import asyncio

        result = asyncio.run(
            fetch_all_activities(
                FakeSession(),
                SimpleNamespace(max_activities=10, activity_page_size=2),
                date(2026, 9, 12),
                date(2026, 9, 23),
                {2},
            )
        )
        self.assertEqual(extract_activity_ids(result), [3])
        self.assertEqual(result["known_items_skipped"], 1)

    def test_hevy_fetches_only_pages_needed_for_new_workout(self) -> None:
        class FakeClient(HevyClient):
            def __init__(self) -> None:
                self.pages = []

            def get(self, path, params=None):
                self.pages.append(params["page"])
                return {
                    "page_count": 3,
                    "workouts": [{"id": "new"}, {"id": "old-1"}],
                }

        client = FakeClient()
        workouts, page_count, fetched = client.get_incremental_workouts(
            [{"id": "old-1"}, {"id": "old-2"}], 3, page_size=2
        )
        self.assertEqual({item["id"] for item in workouts}, {"new", "old-1", "old-2"})
        self.assertEqual((page_count, fetched, client.pages), (1, 2, [1]))

    def test_hevy_deletion_requires_full_reconciliation(self) -> None:
        class FakeClient(HevyClient):
            def __init__(self) -> None:
                self.full_called = False

            def get_all_workouts(self, page_size=10):
                self.full_called = True
                return [{"id": "remaining"}], 1

        client = FakeClient()
        workouts, _, _ = client.get_incremental_workouts(
            [{"id": "removed"}, {"id": "remaining"}], 1
        )
        self.assertTrue(client.full_called)
        self.assertEqual(workouts, [{"id": "remaining"}])

    def test_old_sleep_score_is_not_current_recovery(self) -> None:
        sleep = {"summary": {"latest_daily": {"date": "2026-09-11", "score": 48}}}
        recovery = build_recovery_summary(sleep, "2026-09-23")
        self.assertEqual(recovery["status"], "unknown")
        self.assertIsNone(recovery["score"])
        self.assertEqual(recovery["last_scored_date"], "2026-09-11")


if __name__ == "__main__":
    unittest.main()
