import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard.jobs import JobManager, sleep_schedule_slot
from dashboard.snapshot import TZ
from scripts.import_garmin_mcp_snapshot import extract_sleep, merge_sleep


class SleepRetentionTests(unittest.TestCase):
    def test_nested_garmin_sleep_payload_keeps_recovery_metrics(self):
        payload = {
            'sleep': {
                'daily': [
                    {
                        'date': '2026-10-02',
                        'payload': {
                            'dailySleepDTO': {
                                'calendarDate': '2026-10-02',
                                'sleepTimeSeconds': 27720,
                                'averageRespirationValue': 13.0,
                                'sleepScores': {'overall': {'value': 80, 'qualifierKey': 'GOOD'}},
                            },
                            'avgOvernightHrv': 53.0,
                            'hrvStatus': 'BALANCED',
                            'bodyBatteryChange': 79,
                            'restingHeartRate': 52,
                        },
                    }
                ]
            }
        }
        row = extract_sleep([payload])[0]
        self.assertEqual(row['duration_minutes'], 462)
        self.assertEqual(row['score'], 80)
        self.assertEqual(row['quality'], 'GOOD')
        self.assertEqual(row['resting_hr'], 52)
        self.assertEqual(row['body_battery'], 79)
        self.assertEqual(row['respiration'], 13.0)
        self.assertEqual(row['hrv_ms'], 53.0)
        self.assertEqual(row['hrv_status'], 'BALANCED')

    def test_partial_response_preserves_old_dates_fields_and_zero(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'sleep.json'
            path.write_text(
                json.dumps(
                    {
                        'daily': [
                            {'date': '2026-09-29', 'score': 80, 'duration_minutes': 500},
                            {'date': '2026-09-30', 'score': 70, 'duration_minutes': 460},
                        ]
                    }
                )
            )
            result = merge_sleep(
                path,
                [
                    {'date': '2026-09-30', 'score': None, 'duration_minutes': None},
                    {'date': '2026-10-01', 'score': 0, 'duration_minutes': 400},
                ],
            )
            self.assertEqual(len(result['daily']), 3)
            self.assertEqual(result['daily'][1]['score'], 70)
            self.assertEqual(result['daily'][1]['duration_minutes'], 460)
            self.assertEqual(result['daily'][2]['score'], 0)

    def test_daily_schedule_retry_restart_and_success(self):
        with (
            tempfile.TemporaryDirectory() as name,
            patch.dict(os.environ, {'DASHBOARD_SLEEP_SCHEDULE_ENABLED': 'true'}),
        ):
            root = Path(name)
            manager = JobManager(root / 'runtime', root)
            current = datetime.now(TZ).replace(hour=12, minute=0, second=0, microsecond=0)
            manager.tick_sleep_schedule(current)
            first = manager.list()[0]
            self.assertEqual(first['mode'], 'sync-garmin')
            manager.tick_sleep_schedule(current)
            self.assertEqual(len(manager.list()), 1)
            manager.update(first['id'], 'failed', 'test')
            with manager.db() as conn:
                conn.execute('UPDATE jobs SET finished_at=? WHERE id=?', (current.isoformat(), first['id']))
            restarted = JobManager(root / 'runtime', root)
            restarted.tick_sleep_schedule(current + timedelta(minutes=30))
            self.assertEqual(len(restarted.list()), 1)
            restarted.tick_sleep_schedule(current + timedelta(hours=1))
            self.assertEqual(len(restarted.list()), 2)
            second = next(row for row in restarted.list() if row['status'] == 'queued')
            restarted.update(second['id'], 'completed', 'test')
            restarted.tick_sleep_schedule(current + timedelta(hours=3))
            self.assertEqual(len(restarted.list()), 2)

    def test_slot_before_ten_and_disabled_schedule(self):
        current = datetime(2026, 10, 1, 9, tzinfo=TZ)
        self.assertEqual(sleep_schedule_slot(current).date().isoformat(), '2026-09-30')
        with (
            tempfile.TemporaryDirectory() as name,
            patch.dict(os.environ, {'DASHBOARD_SLEEP_SCHEDULE_ENABLED': 'false'}),
        ):
            root = Path(name)
            manager = JobManager(root / 'runtime', root)
            manager.tick_sleep_schedule(current)
            self.assertEqual(manager.list(), [])
