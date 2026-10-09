import unittest
from datetime import date

from dashboard.daily_analysis import prepare
from dashboard.snapshot import build_snapshot
from dashboard.tests.test_dashboard import Fixture
from scripts.build_performance_management_model import build_recovery_summary
from scripts.sleep_data import summarize_sleep


def sleep_fixture():
    return {'daily': [
        {'date':'2026-09-11', 'score':48},
        {'date':'2026-09-28', 'score':None, 'duration_minutes':None},
        {'date':'2026-09-29', 'duration_minutes':514},
        {'date':'2026-09-30', 'duration_minutes':464},
        {'date':'2026-10-01', 'duration_minutes':446, 'score':90}],
        'summary':{'latest_daily':{'date':'2026-09-11','score':48}}}


class SleepTests(unittest.TestCase):
    def test_duration_without_score_and_actual_calendar_window(self):
        summary = summarize_sleep(sleep_fixture(),'2026-09-30')
        self.assertEqual(summary['latest_daily']['date'],'2026-09-30')
        self.assertEqual(summary['latest_duration_daily']['duration_minutes'],464)
        self.assertEqual(summary['latest_scored_daily']['date'],'2026-09-11')
        self.assertIsNone(summary['last_7_days_average_score'])
        self.assertEqual(summary['last_7_days_average_duration_minutes'],489)
        self.assertEqual(summary['last_7_days_duration_count'],2)

    def test_recovery_keeps_duration_but_not_old_score(self):
        recovery = build_recovery_summary(sleep_fixture(),'2026-09-30')
        self.assertIsNone(recovery['score'])
        self.assertEqual(recovery['status'],'unknown')
        self.assertEqual(recovery['duration_minutes'],464)
        self.assertEqual(recovery['last_duration_date'],'2026-09-30')
        self.assertEqual(recovery['last_scored_date'],'2026-09-11')
        self.assertEqual(build_recovery_summary(sleep_fixture(),'2026-10-01')['score'],90)

    def test_prompt_excludes_future_and_invalidates_old_report(self):
        without = prepare({},date(2026,9,30))
        with_sleep = prepare({'sleep':sleep_fixture()},date(2026,9,30))
        self.assertNotEqual(without['fingerprint'],with_sleep['fingerprint'])
        self.assertNotIn('2026-10-01',with_sleep['prompt'])
        self.assertIn('464',with_sleep['prompt'])
        self.assertEqual(len(with_sleep['context']['sleep']['daily']),2)

    def test_missing_sleep_and_empty_latest_rows(self):
        self.assertIsNone(summarize_sleep({})['latest_daily'])
        data = {'daily':[{'date':'2026-09-29','duration_minutes':0}, {'date':'2026-09-30'}]}
        self.assertEqual(summarize_sleep(data)['latest_daily']['date'],'2026-09-29')
        self.assertEqual(summarize_sleep(data)['last_7_days_average_duration_minutes'],0)


class SleepSnapshotTests(Fixture):
    def test_snapshot_uses_stored_sleep_without_reimport(self):
        self.save('garmin_sleep_reference_2026_04',sleep_fixture())
        self.save('performance_management_model',{'summary':{'recovery':{'score':48}}})
        snapshot = build_snapshot(self.root,date(2026,9,30))
        self.assertIsNone(snapshot['performance']['summary']['recovery']['score'])
        self.assertEqual(snapshot['sleep']['summary']['latest_duration_daily']['duration_minutes'],464)
        self.assertNotIn('2026-10-01',str(snapshot['sleep']))
