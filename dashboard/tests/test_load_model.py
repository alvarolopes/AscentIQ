"""The load model moved from scripts/ to dashboard/ without changing numbers."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'load_model'
TODAY = date(2026, 9, 30)
GENERATED_AT = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone(timedelta(hours=-3)))


def load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding='utf-8'))


def build(training=None, races=None, sleep=None):
    from dashboard.load_model import build_model, collect_activities

    training = load_fixture('training.json') if training is None else training
    races = load_fixture('races.json') if races is None else races
    sleep = load_fixture('sleep.json') if sleep is None else sleep
    activities = collect_activities(training, races)
    return build_model(training, races, sleep, today=TODAY, generated_at=GENERATED_AT), activities


class LoadModelRegressionTests(unittest.TestCase):
    def test_matches_legacy_output(self):
        result, _ = build()
        self.assertIsNotNone(result)
        assert result is not None
        expected = load_fixture('expected.json')
        # Full equality: generated_at is pinned so the whole payload compares.
        self.assertEqual(result.payload['summary']['generated_at'], '2026-09-30T12:00:00-03:00')
        self.assertEqual(result.payload, expected)

    def test_empty_history_returns_none(self):
        from dashboard.load_model import build_model

        self.assertIsNone(build_model([], [], None, today=TODAY, generated_at=GENERATED_AT))

    def test_generated_at_preserves_explicit_timezone(self):
        from dashboard.load_model import build_model

        generated_at = GENERATED_AT.astimezone(UTC)
        result = build_model(load_fixture('training.json'), [], None, today=TODAY, generated_at=generated_at)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.payload['summary']['generated_at'], '2026-09-30T15:00:00+00:00')

    def test_markdown_escapes_untrusted_activity_text_without_changing_payload(self):
        from dashboard.load_model import render_markdown

        result, _ = build()
        daily = result.payload['daily_series']
        activity = next(row['activities'][0] for row in reversed(daily[-7:]) if row['activities'])
        activity['name'] = '<img src=x onerror=alert(1)> [link](javascript:alert(1))\n# injected'
        activity['type'] = '<script>alert(1)</script>'
        markdown = render_markdown(result.payload['summary'], daily)
        self.assertNotIn('<img', markdown)
        self.assertNotIn('<script', markdown)
        self.assertNotIn('[link](javascript:', markdown)
        self.assertNotIn('\n# injected', markdown)
        self.assertIn('&lt;img', markdown)
        self.assertIn(r'\[link\]\(javascript:alert\(1\)\)', markdown)
        self.assertEqual(activity['name'].splitlines()[-1], '# injected')
        activity['type'] = 'Weight Training'
        activity['hevy_total_sets'] = 3
        activity['hevy_classification'] = '<img src=x onerror=alert(1)>'
        self.assertNotIn('<img', render_markdown(result.payload['summary'], daily))

    def test_single_activity_series_runs_until_today(self):
        from dashboard.load_model import build_model

        training = [
            {
                'date': (TODAY - timedelta(days=10)).isoformat(),
                'name': 'Corrida única sintética',
                'type': 'Run',
                'duration_seconds': 2400,
                'distance_km': 8.0,
                'avg_hr': 140,
            }
        ]
        result = build_model(training, [], None, today=TODAY, generated_at=GENERATED_AT)
        self.assertIsNotNone(result)
        assert result is not None
        series = result.payload['daily_series']
        self.assertEqual(len(series), 11)
        self.assertEqual(series[0]['date'], (TODAY - timedelta(days=10)).isoformat())
        self.assertGreater(series[0]['fitness'], 0)
        self.assertLess(series[-1]['fitness'], series[0]['fitness'])
        self.assertTrue(all(row['fitness_ramp_rate_7d'] is None for row in series[:7]))
        self.assertIsInstance(series[7]['fitness_ramp_rate_7d'], (int, float))

    def test_duplicate_between_training_and_race_counts_once(self):
        result, activities = build()
        day = next(row for row in result.payload['daily_series'] if row['date'] == '2026-09-27')
        self.assertEqual(day['activity_count'], 1)
        collected = [item for item in activities if item.get('date') == '2026-09-27']
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0]['model_source'], 'training_history')

    def test_strength_uses_hevy_muscular_load_when_present(self):
        from dashboard.load_model import build_daily_loads, collect_activities

        activities = collect_activities(load_fixture('training.json'), [])
        daily, _ = build_daily_loads(activities, None, today=TODAY)
        day = next(row for row in daily if row['date'] == '2026-09-05')
        load = day['activities'][0]
        self.assertEqual(load['type'], 'Weight Training')
        self.assertIsNone(load['avg_hr'])
        self.assertGreater(load['strength_muscular_load'], 0)
        self.assertGreater(load['estimated_load'], 0)
        self.assertEqual(load['hrr_source'], 'fallback_by_type')
        self.assertEqual(load['hevy_total_volume_kg'], 4200)

    def test_recovery_summary_unknown_without_scores(self):
        from dashboard.load_model import build_recovery_summary

        sleep = {'daily': [{'date': '2026-09-29', 'duration_minutes': 400, 'duration_raw': '6:40'}]}
        self.assertEqual(build_recovery_summary(sleep, '2026-09-30')['status'], 'unknown')


class RebuildTests(unittest.TestCase):
    def test_rebuild_writes_same_artifacts_without_subprocess(self):
        from dashboard.pipeline import rebuild

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / 'data'
            data.mkdir(parents=True)
            (data / 'training_history.json').write_text(
                (FIXTURE_DIR / 'training.json').read_text(encoding='utf-8'), encoding='utf-8'
            )
            (data / 'race_history.json').write_text(
                (FIXTURE_DIR / 'races.json').read_text(encoding='utf-8'), encoding='utf-8'
            )
            (data / 'garmin_sleep_reference_2026_04.json').write_text(
                (FIXTURE_DIR / 'sleep.json').read_text(encoding='utf-8'), encoding='utf-8'
            )
            with patch('dashboard.pipeline.run_script') as run:
                rebuild(root)
            payload = json.loads((data / 'performance_management_model.json').read_text(encoding='utf-8'))
            self.assertTrue(payload['summary']['fitness'])
            self.assertTrue((root / 'analysis' / 'context' / 'performance_management_model.md').exists())
            self.assertTrue((root / 'analysis' / 'context' / 'performance_management_chart.svg').exists())
            self.assertEqual(run.call_count, 4)
            self.assertFalse(
                any('build_performance_management_model' in str(call.args[0]) for call in run.call_args_list)
            )

    def test_rebuild_without_dated_activities_writes_empty_model(self):
        from dashboard.pipeline import rebuild

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / 'data'
            data.mkdir(parents=True)
            (data / 'training_history.json').write_text('[{"name": "sem data"}]', encoding='utf-8')
            with patch('dashboard.pipeline.run_script') as run:
                rebuild(root)
            payload = json.loads((data / 'performance_management_model.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['summary'], {})
            self.assertEqual(payload['daily_series'], [])
            run.assert_not_called()
