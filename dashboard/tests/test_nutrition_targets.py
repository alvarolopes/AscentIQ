"""Automatic daily goals use dated synthetic inputs and no external providers."""

import copy
import json
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard import settings
from dashboard.health import HealthStore, _active_plan, _today
from dashboard.nutrition_targets import NutritionTargets, context_for
from dashboard.tests import pg


class Diary:
    def __init__(self):
        self.days = {}

    def meal(self, day, kcal=2400):
        self.days[day.isoformat()] = {
            'entries': [
                {
                    'id': 'meal-' + day.isoformat(),
                    'text': 'Refeição sintética',
                    'analysis': {'items': [{'name': 'Alimento de exemplo', 'kcal': kcal}]},
                }
            ],
            'completeness': 'complete',
            'fasting_declared': False,
        }

    def read(self, day):
        return copy.deepcopy(
            self.days.get(day.isoformat(), {'entries': [], 'completeness': 'empty', 'fasting_declared': False})
        )

    def read_many(self, days):
        return {day: self.read(day) for day in days}


class NutritionTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = settings.override(
            runtime=self.root / 'runtime',
            ai_provider='ollama',
            ai_enabled=True,
            ollama_model='qwen3.5:4b',
        )
        self.env.__enter__()
        self.addCleanup(self.env.__exit__, None, None, None)
        self.health = HealthStore(self.root / 'runtime', self.root)
        self.day = _today()
        self.health.update('profile', {'age': 43, 'sex': 'male', 'height_cm': 180, 'weight_kg': 80})
        self.health.save(
            'goals',
            {
                'id': 'synthetic-goal',
                'type': 'fat_loss',
                'status': 'active',
                'description': 'Reduzir gordura preservando endurance',
                'priority': 1,
            },
        )
        self.snapshot: dict = {
            'activities': [
                {
                    'id': 'a',
                    'date': self.day.isoformat(),
                    'kind': 'run',
                    'duration_seconds': 3600,
                    'distance_km': 10,
                    'elevation_gain_m': 100,
                }
            ],
            'medical': {'records': ['private medical fixture']},
            'gpx': 'private geometry fixture',
        }
        self.targets = NutritionTargets(self.health, lambda: self.snapshot)
        self.output = json.dumps(
            {
                'energy_adjustment_pct': -0.1,
                'protein_g_per_kg': 1.8,
                'fat_energy_fraction': 0.30,
                'reason': 'Estimativa sintética para o objetivo e treino.',
                'limitations': ['Referência estimada.'],
            }
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_generates_calories_macros_dated_plan_and_reuses_unchanged_context(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output) as infer:
            self.targets.refresh(self.day)
            first = self.targets.view(self.day)
            self.assertEqual(first['status'], 'ready')
            self.assertEqual(first['protein_g'], 144)
            self.assertGreater(first['kcal'], 1700)
            self.assertAlmostEqual(
                first['kcal'], first['protein_g'] * 4 + first['carbs_g'] * 4 + first['fat_g'] * 9, delta=2
            )
            context = json.loads(infer.call_args.args[1])
            self.assertEqual(context['profile']['weight_kg'], 80)
            self.assertEqual(context['goal']['id'], 'synthetic-goal')
            self.assertNotIn('effective_from', context['goal'])
            self.assertEqual(len(context['activities_14_days']), 1)
            self.assertEqual(len(context['activities_today']), 1)
            self.assertEqual(context['method'], 'daily_local_ai_targets_v2')
            self.assertAlmostEqual(first['fat_g'] * 9 / first['kcal'], 0.30, delta=0.001)
            self.assertNotIn('medical', context)
            self.assertNotIn('gpx', context)
            self.assertNotIn('food', context)
            self.assertNotIn('Referência estimada.', first['limitations'])
            self.assertTrue(any('tendência' in text for text in first['limitations']))
            self.targets.refresh(self.day)
            self.assertEqual(infer.call_count, 1)
        plan = _active_plan(self.health.read(), self.day)
        self.assertEqual(plan['source'], 'ollama')
        self.assertEqual(plan['effective_from'], self.day.isoformat())
        self.assertEqual(plan['next_review_date'], (self.day + timedelta(days=1)).isoformat())

    def test_new_day_and_weight_change_publish_new_versions_without_rewriting_history(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output) as infer:
            self.targets.refresh(self.day)
            before = self.targets.view(self.day)
            tomorrow = self.day + timedelta(days=1)
            self.health.save('measurements', {'id': 'future-weight', 'date': tomorrow.isoformat(), 'weight_kg': 78})
            self.targets.refresh(self.day)
            self.assertEqual(infer.call_count, 1)
            with patch('dashboard.nutrition_targets._today', return_value=tomorrow):
                self.targets.refresh(tomorrow)
            after = self.targets.view(tomorrow)
            self.assertEqual(after['protein_g'], 140.4)
            self.assertEqual(self.targets.view(self.day)['protein_g'], before['protein_g'])
            self.assertEqual(infer.call_count, 2)

    def test_missing_profile_disabled_provider_and_paused_setting_never_call_ai(self):
        with pg.temp_database():
            missing = HealthStore(self.root / 'empty', self.root)
            service = NutritionTargets(missing, lambda: {})
            with patch('dashboard.nutrition_targets.request_text') as infer:
                service.refresh(self.day)
                self.assertEqual(service.view(self.day)['status'], 'missing_data')
                self.assertIsNone(service.view(self.day)['kcal'])
        with patch('dashboard.nutrition_targets.request_text') as infer:
            with settings.override(ai_provider='openai', openai_api_key='synthetic-unused'):
                self.targets.refresh(self.day)
            self.assertEqual(self.targets.view(self.day)['status'], 'unavailable')
            self.health.update('preferences', {'auto_nutrition_targets': False})
            self.targets.refresh(self.day)
            self.assertEqual(self.targets.view(self.day)['status'], 'paused')
            infer.assert_not_called()

    def test_invalid_response_and_inference_failure_preserve_last_plan(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            self.targets.refresh(self.day)
        before = self.targets.view(self.day)
        self.snapshot['activities'].append(
            {'id': 'b', 'date': self.day.isoformat(), 'kind': 'strength', 'duration_seconds': 1800}
        )
        for output in (
            '{}',
            '{"energy_adjustment_pct":-0.8,"protein_g_per_kg":1.8}',
            '{"energy_adjustment_pct":true,"protein_g_per_kg":1.8}',
        ):
            with patch('dashboard.nutrition_targets.request_text', return_value=output):
                self.targets.refresh(self.day, force=True)
            self.assertEqual(self.targets.view(self.day)['kcal'], before['kcal'])
            self.assertEqual(self.targets.status, 'error')
        with patch('dashboard.nutrition_targets.request_text', side_effect=RuntimeError('Ollama local não respondeu')):
            self.targets.refresh(self.day, force=True)
        self.assertEqual(self.targets.view(self.day)['protein_g'], before['protein_g'])

    def test_concurrent_profile_change_cancels_publication_and_alert_blocks_deficit(self):
        before = len(self.health.read()['plans'])

        def changed(*args, **kwargs):
            self.health.update('profile', {'height_cm': 185})
            return self.output

        with patch('dashboard.nutrition_targets.request_text', side_effect=changed):
            self.targets.refresh(self.day)
        self.assertEqual(len(self.health.read()['plans']), before)
        self.assertEqual(self.targets.status, 'error')
        self.health.save('checkins', {'id': 'ill', 'date': self.day.isoformat(), 'illness': True})
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        self.assertEqual(context['limits']['min_adjustment'], 0)
        self.assertTrue(context['recovery_alert'])
        reference_kcal = context['energy_reference']['total_kcal']
        output = {**json.loads(self.output), 'energy_adjustment_pct': -0.08}
        with patch('dashboard.nutrition_targets.request_text', return_value=json.dumps(output)):
            self.targets.refresh(self.day, force=True)
        self.assertEqual(self.targets.status, 'ready')
        plan = _active_plan(self.health.read(), self.day)
        minimum = max(
            context['limits']['min_target_kcal'],
            context['energy_reference'].get('resting_kcal') or 0,
            reference_kcal,
        )
        floor = math.ceil(minimum / 50) * 50
        self.assertEqual(plan['target_kcal'], max(floor, round(reference_kcal / 50) * 50))
        self.assertEqual(plan['requested_adjustment_pct'], -0.08)
        self.assertEqual(plan['applied_adjustment_pct'], 0)
        self.assertIn('limite vigente', plan['reason'])
        self.assertIn('recuperação', plan['reason'])

    def test_out_of_range_adjustment_is_clamped_and_recorded_not_rejected(self):
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        reference_kcal = context['energy_reference']['total_kcal']
        upper = math.floor(reference_kcal * 1.10 / 50) * 50
        output = {**json.loads(self.output), 'energy_adjustment_pct': 0.5}
        with patch('dashboard.nutrition_targets.request_text', return_value=json.dumps(output)):
            self.targets.refresh(self.day, force=True)
        self.assertEqual(self.targets.status, 'ready')
        plan = _active_plan(self.health.read(), self.day)
        self.assertEqual(plan['target_kcal'], upper)
        self.assertEqual(plan['requested_adjustment_pct'], 0.5)
        self.assertEqual(plan['applied_adjustment_pct'], 0.10)
        self.assertIn('limite vigente', plan['reason'])
        self.assertIn('política do produto', plan['reason'])

    def test_non_numeric_adjustment_still_preserves_the_previous_plan(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            self.targets.refresh(self.day)
        before = _active_plan(self.health.read(), self.day)['id']
        for index, bad in enumerate(('"abc"', 'NaN', 'null', 'true')):
            # A changed context bypasses the fingerprint reuse and reaches the AI.
            self.snapshot['activities'].append(
                {'id': f'bad-{index}', 'date': self.day.isoformat(), 'kind': 'run', 'duration_seconds': 60}
            )
            raw = self.output.replace('"energy_adjustment_pct": -0.1', f'"energy_adjustment_pct": {bad}')
            with patch('dashboard.nutrition_targets.request_text', return_value=raw):
                self.targets.refresh(self.day, force=True)
            self.assertEqual(self.targets.status, 'error')
            self.assertEqual(_active_plan(self.health.read(), self.day)['id'], before)
            self.assertNotIn('requested_adjustment_pct', _active_plan(self.health.read(), self.day))

    def test_future_generation_and_invalid_preference_are_rejected(self):
        with patch('dashboard.nutrition_targets.request_text') as infer:
            self.targets.refresh(self.day + timedelta(days=1))
            self.assertEqual(self.targets.status, 'error')
            infer.assert_not_called()
        with self.assertRaises(ValueError):
            self.health.update('preferences', {'auto_nutrition_targets': 'false'})

    def test_activity_change_during_inference_cancels_stale_publication(self):
        before = len(self.health.read()['plans'])

        def changed(*args, **kwargs):
            self.snapshot['activities'].append(
                {'id': 'late-import', 'date': self.day.isoformat(), 'kind': 'running', 'duration_seconds': 7200}
            )
            return self.output

        with patch('dashboard.nutrition_targets.request_text', side_effect=changed):
            self.targets.refresh(self.day)
        self.assertEqual(len(self.health.read()['plans']), before)
        self.assertEqual(self.targets.status, 'error')

    def test_daily_publication_preserves_an_existing_future_plan(self):
        tomorrow = self.day + timedelta(days=1)
        self.health.save(
            'plans',
            {
                'id': 'future-plan',
                'goal_id': 'synthetic-goal',
                'target_kcal': 2400,
                'protein_g': 150,
                'effective_from': tomorrow.isoformat(),
            },
        )
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            self.targets.refresh(self.day)
        self.assertEqual(self.targets.view(self.day)['status'], 'ready')
        self.assertEqual(self.targets.view(tomorrow)['kcal'], 2400)
        self.assertEqual(self.targets.view(tomorrow)['protein_g'], 150)

    def test_invalid_fat_distribution_preserves_existing_plan(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            self.targets.refresh(self.day)
        before = _active_plan(self.health.read(), self.day)['id']
        self.snapshot['activities'][0]['duration_seconds'] = 7200
        for fraction in (None, True, 0.20, 0.50):
            output = {**json.loads(self.output), 'fat_energy_fraction': fraction}
            with patch('dashboard.nutrition_targets.request_text', return_value=json.dumps(output)):
                self.targets.refresh(self.day, force=True)
            self.assertEqual(self.targets.status, 'error')
            self.assertEqual(_active_plan(self.health.read(), self.day)['id'], before)

    def test_weight_context_excludes_future_and_old_measurements(self):
        for identifier, offset, weight in (('old', -35, 83), ('recent', -7, 81), ('future', 1, 79)):
            self.health.save(
                'measurements',
                {'id': identifier, 'date': (self.day + timedelta(days=offset)).isoformat(), 'weight_kg': weight},
            )
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        self.assertEqual(
            context['weight_history_30_days'], [{'date': (self.day - timedelta(days=7)).isoformat(), 'weight_kg': 81}]
        )

    def test_unverified_clinical_claim_is_omitted_but_valid_targets_are_published(self):
        output = {**json.loads(self.output), 'reason': 'A distribuição garante estabilidade hormonal.'}
        with patch('dashboard.nutrition_targets.request_text', return_value=json.dumps(output)):
            self.targets.refresh(self.day)
        self.assertEqual(self.targets.status, 'ready')
        plan = _active_plan(self.health.read(), self.day)
        self.assertNotIn('estabilidade hormonal', plan['reason'])
        self.assertIn('Meta:', plan['reason'])
        self.assertEqual(plan['protein_g'], 144)

    def garmin_days(self, count, total=2700, end=None):
        end = end or self.day - timedelta(days=1)
        return [
            {
                'date': (end - timedelta(days=offset)).isoformat(),
                'total_kcal': total + offset,
                'resting_kcal': 1900,
                'source': 'garmin',
                'coverage': 'complete',
                'coverage_hours': 24,
            }
            for offset in range(count)
        ]

    def test_wearable_recent_mean_is_the_primary_reference(self):
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(10)}
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output) as infer:
            self.targets.refresh(self.day)
            self.assertEqual(self.targets.status, 'ready')
            context = json.loads(infer.call_args.args[1])
            reference = context['energy_reference']
            expected = round(sum(2700 + o for o in range(10)) / 10)
            self.assertEqual(reference['source'], 'garmin_recent_mean')
            self.assertEqual(reference['total_kcal'], expected)
            self.assertEqual(reference['days_used'], 10)
            self.assertEqual(context['prompt_revision'], 4)
            self.assertEqual(context['energy_reference_alternatives'][0]['source'], 'profile_model')
            self.assertEqual(context['calibration']['status'], 'unavailable')
        plan = _active_plan(self.health.read(), self.day)
        self.assertEqual(plan['baseline_source'], 'garmin_recent_mean')
        self.assertEqual(plan['baseline_method'], 'wearable_recent_mean_14d_v1')
        self.assertEqual(plan['baseline_expenditure_kcal'], expected)
        self.assertIn('média do relógio', plan['reason'])
        self.assertNotIn('Fator de atividade estimado', ' '.join(plan['limitations']))
        view = self.targets.view(self.day)
        self.assertEqual(view['baseline_source'], 'garmin_recent_mean')
        self.assertEqual(view['baseline_kcal'], expected)

    def test_five_wearable_days_fall_back_to_the_profile_model(self):
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(5)}
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        self.assertEqual(context['energy_reference']['source'], 'profile_model')
        self.assertEqual(context['energy_reference_alternatives'], [])

    def test_wearable_method_without_enough_days_never_calls_ai(self):
        self.health.update('preferences', {'energy_method': 'wearable'})
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(5)}
        with patch('dashboard.nutrition_targets.request_text') as infer:
            self.targets.refresh(self.day)
            self.assertEqual(self.targets.view(self.day)['status'], 'missing_data')
            self.assertTrue(any('relógio' in text for text in self.targets.missing))
            infer.assert_not_called()

    def test_model_method_ignores_wearable_rows(self):
        self.health.update('preferences', {'energy_method': 'model'})
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(10)}
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        self.assertEqual(context['energy_reference']['source'], 'profile_model')
        self.assertEqual(context['energy_reference_alternatives'][0]['source'], 'garmin_recent_mean')

    def test_insufficient_calibration_is_declared_as_a_limitation(self):
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(10)}
        diary = Diary()
        targets = NutritionTargets(self.health, lambda: self.snapshot, diary=diary)
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            targets.refresh(self.day)
        self.assertEqual(targets.status, 'ready')
        plan = _active_plan(self.health.read(), self.day)
        self.assertEqual(plan['calibration']['status'], 'insufficient')
        self.assertTrue(any('Calibração por ingestão e tendência de peso' in t for t in plan['limitations']))

    def test_applied_calibration_shifts_the_reference_within_the_clamp(self):
        diary = Diary()
        for offset in range(1, 15):
            diary.meal(self.day - timedelta(days=offset), kcal=2400)
        self.snapshot['daily_energy'] = {'daily': self.garmin_days(14, total=2700)}
        for index, day in enumerate(range(24, 0, -7)):
            self.health.save(
                'measurements',
                {'id': f'w{index}', 'date': (self.day - timedelta(days=day)).isoformat(), 'weight_kg': 80.0},
            )
        targets = NutritionTargets(self.health, lambda: self.snapshot, diary=diary)
        _, context, _, _ = context_for(self.health, self.snapshot, self.day, diary)
        self.assertEqual(context['calibration']['status'], 'applied')
        reference = context['energy_reference']
        self.assertIn('intake_weight_trend_calibration_v1', reference['method'])
        self.assertEqual(reference['total_kcal'], context['calibration']['calibrated_kcal'])
        self.assertLess(abs(reference['total_kcal'] - context['calibration']['implied_tdee_kcal']), 1000)
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            targets.refresh(self.day)
        self.assertEqual(targets.status, 'ready')
        plan = _active_plan(self.health.read(), self.day)
        self.assertEqual(plan['calibration']['status'], 'applied')
        self.assertEqual(plan['baseline_source'], 'garmin_recent_mean')
