"""Automatic daily goals use dated synthetic inputs and no external providers."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard.health import HealthStore, _active_plan, _today
from dashboard.nutrition_targets import NutritionTargets, context_for


class NutritionTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'DATABASE_BACKEND': 'json', 'ASCENTIQ_AI_PROVIDER': 'ollama',
                              'ASCENTIQ_AI_ENABLED': 'true', 'OLLAMA_MODEL': 'qwen3.5:4b'})
        self.env.start()
        self.health = HealthStore(self.root / 'runtime', self.root)
        self.day = _today()
        self.health.update('profile', {'age': 43, 'sex': 'male', 'height_cm': 180, 'weight_kg': 80})
        self.health.save('goals', {'id': 'synthetic-goal', 'type': 'fat_loss', 'status': 'active',
                         'description': 'Reduzir gordura preservando endurance', 'priority': 1})
        self.snapshot = {'activities': [{'id': 'a', 'date': self.day.isoformat(), 'kind': 'run',
                         'duration_seconds': 3600, 'distance_km': 10, 'elevation_gain_m': 100}],
                         'medical': {'records': ['private medical fixture']}, 'gpx': 'private geometry fixture'}
        self.targets = NutritionTargets(self.health, lambda: self.snapshot)
        self.output = json.dumps({'energy_adjustment_pct': -0.1, 'protein_g_per_kg': 1.8,
                                 'fat_energy_fraction': 0.30,
                                 'reason': 'Estimativa sintética para o objetivo e treino.', 'limitations': ['Referência estimada.']})

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_generates_calories_macros_dated_plan_and_reuses_unchanged_context(self):
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output) as infer:
            self.targets.refresh(self.day)
            first = self.targets.view(self.day)
            self.assertEqual(first['status'], 'ready')
            self.assertEqual(first['protein_g'], 144)
            self.assertGreater(first['kcal'], 1700)
            self.assertAlmostEqual(first['kcal'], first['protein_g'] * 4 + first['carbs_g'] * 4 + first['fat_g'] * 9, delta=2)
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
        missing = HealthStore(self.root / 'empty', self.root)
        service = NutritionTargets(missing, lambda: {})
        with patch('dashboard.nutrition_targets.request_text') as infer:
            service.refresh(self.day)
            self.assertEqual(service.view(self.day)['status'], 'missing_data')
            self.assertIsNone(service.view(self.day)['kcal'])
            with patch.dict(os.environ, {'ASCENTIQ_AI_PROVIDER': 'openai', 'OPENAI_API_KEY': 'synthetic-unused'}):
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
        self.snapshot['activities'].append({'id': 'b', 'date': self.day.isoformat(), 'kind': 'strength', 'duration_seconds': 1800})
        for output in ('{}', '{"energy_adjustment_pct":-0.8,"protein_g_per_kg":1.8}',
                       '{"energy_adjustment_pct":true,"protein_g_per_kg":1.8}'):
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
        with patch('dashboard.nutrition_targets.request_text', return_value=self.output):
            self.targets.refresh(self.day, force=True)
        self.assertEqual(len(self.health.read()['plans']), before)

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
            self.snapshot['activities'].append({'id': 'late-import', 'date': self.day.isoformat(),
                                               'kind': 'running', 'duration_seconds': 7200})
            return self.output
        with patch('dashboard.nutrition_targets.request_text', side_effect=changed):
            self.targets.refresh(self.day)
        self.assertEqual(len(self.health.read()['plans']), before)
        self.assertEqual(self.targets.status, 'error')

    def test_daily_publication_preserves_an_existing_future_plan(self):
        tomorrow = self.day + timedelta(days=1)
        self.health.save('plans', {'id': 'future-plan', 'goal_id': 'synthetic-goal',
                         'target_kcal': 2400, 'protein_g': 150, 'effective_from': tomorrow.isoformat()})
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
            self.health.save('measurements', {'id': identifier, 'date': (self.day + timedelta(days=offset)).isoformat(),
                                             'weight_kg': weight})
        _, context, _, _ = context_for(self.health, self.snapshot, self.day)
        self.assertEqual(context['weight_history_30_days'], [{'date': (self.day - timedelta(days=7)).isoformat(), 'weight_kg': 81}])

    def test_unverified_clinical_claim_does_not_publish_plan(self):
        before = self.health.read()['plans']
        output = {**json.loads(self.output), 'reason': 'A distribuição garante estabilidade hormonal.'}
        with patch('dashboard.nutrition_targets.request_text', return_value=json.dumps(output)):
            self.targets.refresh(self.day)
        self.assertEqual(self.targets.status, 'error')
        self.assertEqual(self.health.read()['plans'], before)
