"""Clock, coverage and privacy regressions for synthetic daily coaching context."""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from dashboard.day_review import SECTIONS, interpretation_context, prepare, render_response
from dashboard.food_store import FoodDiary
from dashboard.health import HealthStore
from dashboard.tests import pg


class DayReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.day = date(2026, 10, 5)
        self.now = datetime(2026, 10, 5, 20, 15, tzinfo=ZoneInfo('America/Sao_Paulo'))
        self.health = HealthStore(self.root / 'runtime', self.root)
        self.health.update(
            'profile', {'age': 43, 'height_cm': 180, 'sex': 'male', 'weight_kg': 80, 'effective_from': '2026-09-01'}
        )
        self.health.update(
            'preferences',
            {
                'activity_factor': 1.55,
                'allergies': 'amendoim',
                'food_preferences': 'vegetariano',
                'effective_from': '2026-09-01',
            },
        )
        self.health.save(
            'goals',
            {
                'id': 'goal',
                'type': 'fat_loss',
                'description': 'Objetivo de teste',
                'target_kcal': 2400,
                'effective_from': '2026-09-01',
            },
        )
        self.diary = FoodDiary(self.root / 'runtime', self.root)
        self.diary.change(
            self.day,
            {
                'id': 'meal',
                'meal': 'Jantar',
                'text': 'Refeição sintética',
                'image_id': 'private-photo-marker',
                'analysis': {
                    'items': [{'name': 'Exemplo', 'kcal': 500, 'protein_g': 30, 'carbs_g': 50, 'fat_g': 20}],
                    'notes': 'Porção estimada.',
                },
            },
        )
        self.snapshot = {
            'activities': [
                {
                    'id': 'run',
                    'date': '2026-10-05',
                    'kind': 'running',
                    'duration_seconds': 3600,
                    'distance_km': 10,
                    'date_time': '2026-10-05T17:00:00-03:00',
                    'geometry': 'private-geometry-marker',
                },
                {'id': 'g1', 'date': '2026-10-05', 'kind': 'strength'},
                {'id': 'future-marker', 'date': '2026-10-06', 'kind': 'running'},
            ],
            'strength': [{'id': 'h1', 'date': '2026-10-05', 'garmin_activity_ids': ['g1']}],
            'medical': {'secret': 'private-medical-marker'},
        }

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **kwargs):
        return prepare(
            self.day,
            self.snapshot,
            self.health.read(),
            self.health.summary(self.day, self.snapshot, self.diary),
            self.diary,
            now=kwargs.pop('now', self.now),
            **kwargs,
        )

    def test_late_low_subtotal_is_not_a_confirmed_deficit_and_training_is_not_duplicated(self):
        result = self.prepare(notes='Já jantei, sem fome; pouca energia na corrida.')
        context = result['context']
        self.assertEqual(context['clock']['local_hour'], 20)
        self.assertEqual(context['review_signal']['code'], 'late_low_recorded')
        self.assertEqual(context['food']['remaining_to_target_kcal'], 1900)
        self.assertEqual(context['food']['completeness'], 'partial')
        self.assertIsNone(context['estimated_deficit_kcal'])
        self.assertEqual(context['training']['session_count'], 2)
        self.assertEqual(len(context['training']['activities']), 1)
        self.assertEqual(context['preferences']['allergies'], 'amendoim')
        self.assertEqual(context['preferences']['food_preferences'], 'vegetariano')
        self.assertNotIn('Jantar', context['food']['unrecorded_meal_labels'])
        for marker in ('private-photo-marker', 'private-geometry-marker', 'private-medical-marker', 'future-marker'):
            self.assertNotIn(marker, result['prompt'])
        self.assertTrue(context['food']['timestamps_are_registration_times'])
        self.assertTrue(context['food']['meal_labels_are_not_required'])
        self.assertTrue(context['food']['entries_are_recorded_as_consumed'])
        self.assertTrue(context['food']['available_estimates_are_already_in_totals'])

    def test_clock_updates_cache_but_not_data_fingerprint_and_morning_is_not_late(self):
        evening = self.prepare()
        morning = self.prepare(now=self.now.replace(hour=9))
        self.assertIsNone(morning['context']['review_signal'])
        self.assertNotEqual(morning['fingerprint'], evening['fingerprint'])
        self.assertEqual(morning['data_fingerprint'], evening['data_fingerprint'])
        historic = self.prepare(now=self.now.replace(day=6))
        self.assertEqual(historic['context']['clock']['mode'], 'historical_day')
        self.assertIsNone(historic['context']['clock']['local_hour'])
        self.assertIsNone(historic['context']['review_signal'])
        with self.assertRaises(ValueError):
            self.prepare(now=self.now.replace(day=4))

    def test_unknown_intake_never_becomes_zero_and_changes_make_data_stale(self):
        before = self.prepare()['data_fingerprint']
        self.diary.change(self.day, {'id': 'meal', 'meal': 'Jantar', 'text': 'Ainda sem quantidades', 'analysis': None})
        result = self.prepare()
        self.assertIsNone(result['context']['food']['registered_kcal'])
        self.assertIsNone(result['context']['food']['recorded_fraction_of_target'])
        self.assertIsNone(result['context']['estimated_deficit_kcal'])
        self.assertEqual(result['context']['food']['pending_count'], 1)
        self.assertNotEqual(before, result['data_fingerprint'])
        self.assertIn('proteína não disponível', result['context']['facts_summary'])

    def test_planning_is_dated_and_does_not_become_an_executed_session(self):
        result = self.prepare(
            planning=[
                {'date': '2026-10-05', 'type': 'training', 'title': 'Planejado', 'status': 'planned'},
                {'date': '2026-10-06', 'title': 'future-plan-marker'},
            ]
        )
        self.assertEqual(result['context']['training']['session_count'], 2)
        self.assertEqual(len(result['context']['planning_today']), 1)
        self.assertNotIn('future-plan-marker', result['prompt'])
        for notes in [True, [], 'x' * 3001]:
            with self.assertRaises(ValueError):
                self.prepare(notes=notes)

    def test_confirmed_large_estimated_deficit_requires_usable_coverage(self):
        self.diary.change(self.day, completeness='complete')
        summary = self.health.summary(self.day, self.snapshot, self.diary)
        summary['energy'] = {'usable': True, 'registered_kcal': 500, 'expenditure_kcal': 3000, 'deficit_kcal': 2500}
        result = prepare(self.day, self.snapshot, self.health.read(), summary, self.diary, now=self.now)
        self.assertEqual(result['context']['review_signal']['code'], 'large_estimated_deficit')
        summary['energy']['usable'] = False
        result = prepare(self.day, self.snapshot, self.health.read(), summary, self.diary, now=self.now)
        self.assertIsNone(result['context']['estimated_deficit_kcal'])
        self.assertEqual(result['context']['review_signal']['code'], 'late_low_recorded')
        summary['energy']['usable'] = True
        self.diary.change(self.day, completeness='partial')
        result = prepare(self.day, self.snapshot, self.health.read(), summary, self.diary, now=self.now)
        self.assertIsNone(result['context']['estimated_deficit_kcal'])

    def test_report_uses_local_arithmetic_and_rejects_ai_numbers_or_invalid_sections(self):
        context = self.prepare()['context']
        sections = {
            key: 'Texto sintético com hipóteses e opções condicionais, sem números inventados.' for key in SECTIONS
        }
        rendered = render_response(context, json.dumps(sections))
        self.assertIn('Diferença para a meta: 1.900 kcal', rendered)
        self.assertIn('Refeições já registradas: Jantar.', rendered)
        self.assertIn('Déficit do dia: não determinável', rendered)
        for invalid in (
            'texto fora do formato',
            '[]',
            '{}',
            json.dumps({**sections, 'opcoes_agora': 'Coma 1900 kcal agora.'}),
            json.dumps({**sections, 'limites': True}),
        ):
            with self.assertRaises(RuntimeError):
                render_response(context, invalid)

    def test_local_only_request_cannot_switch_to_paid_transport(self):
        from dashboard.assistant import request_text

        with (
            patch('dashboard.assistant.configuration', return_value={'provider': 'openai', 'configured': True}),
            patch(
                'dashboard.local_ai.request_text', side_effect=ValueError('O modelo local não está configurado.')
            ) as local,
            patch('dashboard.assistant.urlopen') as paid,
        ):
            with self.assertRaises(ValueError):
                request_text('Instruções sintéticas', 'Contexto sintético', local_only=True)
            local.assert_called_once()
            paid.assert_not_called()

    def test_small_model_receives_comparisons_and_keeps_exact_metrics_in_local_facts(self):
        result = self.prepare(notes='Já jantei e tive pouca energia na corrida.')
        context = interpretation_context(result['context'])
        self.assertEqual(context['food']['registered_energy_vs_target'], 'abaixo da referência estimada')
        self.assertEqual(context['food']['nutrients_vs_targets']['carbs_g'], 'desconhecido')
        known = {**result['context'], 'plan': {**result['context']['plan'], 'carbs_g': 300}}
        self.assertEqual(
            interpretation_context(known)['food']['nutrients_vs_targets']['carbs_g'], 'abaixo da referência estimada'
        )
        self.assertFalse(context['energy']['usable_for_daily_balance'])
        self.assertEqual(context['training']['modalities_today'], ['running', 'strength'])
        self.assertTrue(context['training']['time_order_intensity_and_weather_are_not_provided'])
        self.assertEqual(context['preferences']['allergies'], 'amendoim')
        self.assertNotIn('500', result['prompt'])
        self.assertNotIn('2400', result['prompt'])
        self.assertIn('500 kcal', result['context']['facts_summary'])
        self.diary.change(
            self.day,
            {
                'id': 'missing-macro',
                'meal': 'Lanche',
                'text': 'Nutriente desconhecido',
                'analysis': {'items': [{'name': 'Exemplo', 'kcal': 100, 'carbs_g': None}]},
            },
        )
        incomplete = self.prepare()['context']
        incomplete['plan']['carbs_g'] = 300
        self.assertEqual(interpretation_context(incomplete)['food']['nutrients_vs_targets']['carbs_g'], 'desconhecido')
        self.diary.change(self.day, remove='missing-macro')
        self.diary.change(self.day, {'id': 'meal', 'meal': 'Jantar', 'text': 'Pendente', 'analysis': None})
        pending = interpretation_context(self.prepare()['context'])
        self.assertEqual(pending['food']['registered_energy_vs_target'], 'desconhecido')
        self.assertTrue(pending['food']['has_pending_estimates'])
