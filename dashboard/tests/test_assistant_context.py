"""Context selection and conversation isolation, using synthetic records only."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard.artifacts import Artifacts
from dashboard.assistant import (
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_TOKENS,
    _estimated_tokens,
    answer,
    personal_period,
    prepare_personal,
)


class Diary:
    def read(self, day):
        return {
            'date': day.isoformat(),
            'entries': [
                {
                    'meal': 'Almoço',
                    'text': 'Refeição sintética',
                    'image': 'PRIVATE_PHOTO',
                    'analysis': {'items': [{'kcal': 500, 'protein_g': 35, 'carbs_g': 50, 'fat_g': 18}]},
                }
            ],
            'totals': {'kcal': 500, 'protein_g': 35, 'carbs_g': 50, 'fat_g': 18},
            'completeness': 'partial',
            'pending_count': 0,
            'unknown_nutrients': {},
            'fasting_declared': False,
            'complete_nutrition': False,
        }

    def read_many(self, days):
        return {day: self.read(day) for day in days}


def metric(summary, name):
    if 'rows' in summary:
        row = next(row for row in summary['rows'] if row[0] == name)
        return dict(zip(summary['columns'][1:], row[1:]))
    return summary[name]


class AssistantContextTests(unittest.TestCase):
    def prepared(self, scope=None):
        return {
            'fingerprint': 'synthetic',
            'prompt': 'Current synthetic data',
            'context': {'profile': {'timezone': 'America/Sao_Paulo'}},
            'scope': scope or ['profile'],
        }

    def test_month_is_a_calendar_range_including_leap_day(self):
        first, last, days = personal_period(date(2024, 2, 15), period='month')
        self.assertEqual((first, last, days), (date(2024, 2, 1), date(2024, 2, 29), 29))
        with self.assertRaises(ValueError):
            personal_period(date(2024, 2, 15), period='custom', start='2024-02-15', end='2024-02-01')

    def test_selected_details_keep_whole_period_totals_and_exclude_credentials(self):
        day = date(2024, 2, 29)
        state: dict = {'goals': [], 'plans': [], 'measurements': [], 'checkins': [], 'decisions': []}
        activities = [
            {
                'id': str(i),
                'date': day.isoformat(),
                'name': 'Synthetic activity ' + 'x' * 900,
                'duration_seconds': 600,
                'kind': 'running',
                'distance_km': 1,
            }
            for i in range(40)
        ]
        result = prepare_personal(
            day,
            29,
            {'activities': activities},
            state,
            {
                'profile': {'weight_kg': 80, 'credentials': {'password': 'NEVER_SEND_SECRET'}},
                'active_plan': {
                    'target_kcal': 2400,
                    'protein_g': 160,
                    'carbs_g': 260,
                    'fat_g': 80,
                    'nutrition_context': {'api_key': 'NEVER_SEND_SECRET'},
                },
            },
            Diary(),
            period='month',
        )
        context = result['context']
        self.assertEqual(context['training_summary']['activity_count'], 40)
        self.assertEqual(context['training_summary']['running_km'], 40)
        self.assertEqual(len(context['food']['rows']), 29)
        self.assertEqual(context['food']['rows'][0][0], '2024-02-01')
        self.assertEqual(sum(row[1] for row in context['food']['rows']), 29 * 500)
        self.assertEqual(context['active_plan']['protein_g'], 160)
        self.assertLess(context['selection']['activities_included'], 40)
        self.assertEqual(context['selection']['meal_detail_count'], 29)
        self.assertNotIn('NEVER_SEND_SECRET', result['prompt'])
        self.assertNotIn('PRIVATE_PHOTO', result['prompt'])
        self.assertLessEqual(
            len(json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()),
            MAX_CONTEXT_BYTES,
        )

    def test_unestimated_meal_does_not_become_zero_nutrients(self):
        class Pending(Diary):
            def read(self, day):
                result = super().read(day)
                result['entries'][0]['analysis'] = None
                result['pending_count'] = 1
                return result

        state: dict = {'goals': [], 'plans': [], 'measurements': [], 'checkins': [], 'decisions': []}
        prepared = prepare_personal(date(2024, 2, 1), 1, {}, state, {}, Pending())
        self.assertIsNone(prepared['context']['meal_details'][0]['totals']['protein_g'])

    def test_long_plan_and_body_report_keep_month_usable(self):
        day = date(2024, 2, 29)
        dates = [(day - timedelta(days=i)).isoformat() for i in range(28, -1, -1)]
        state: dict = {'goals': [], 'plans': [], 'measurements': [], 'checkins': [], 'decisions': []}
        snapshot = {
            'body': {
                'reference_date': '2024-01-01',
                'current': {'weight_kg': 80, **{f'measurement_{i}': 12.34 for i in range(40)}},
                'skinfolds_current_mm': {f'site_{i}': 10.5 for i in range(20)},
            }
        }
        plan = {
            'id': 'synthetic-plan',
            'target_kcal': 2400,
            'protein_g': 160,
            'reason': 'Synthetic rationale with assumptions and alternatives. ' * 35,
            'limitations': ['Synthetic limitation about coverage. ' * 3 for _ in range(9)],
        }
        summary = {
            'active_plan': plan,
            'series': [
                {
                    'date': value,
                    'expenditure_kcal': 2800,
                    'expenditure_status': 'available',
                    'intake_kcal': 500,
                    'usable': False,
                }
                for value in dates
            ],
        }
        result = prepare_personal(day, 29, snapshot, state, summary, Diary(), period='month')
        context = result['context']
        self.assertEqual(context['active_plan']['target_kcal'], 2400)
        self.assertEqual(context['active_plan']['protein_g'], 160)
        self.assertEqual(context['body_reference']['current']['weight_kg'], 80)
        self.assertEqual(context['body_reference']['reference_date'], '2024-01-01')
        if context['selection']['plan_rationale_included']:
            self.assertEqual(context['active_plan']['reason'], plan['reason'])
        else:
            self.assertNotIn('reason', context['active_plan'])
        self.assertFalse(context['selection']['body_details_included'])
        self.assertEqual(metric(context['period_summaries']['registered_food'], 'kcal')['sum_registered'], 14500)
        self.assertLessEqual(_estimated_tokens(json.dumps(context, ensure_ascii=False)), MAX_CONTEXT_TOKENS)

    def test_dense_ninety_day_period_keeps_aggregate_facts_with_explicit_selection(self):
        day = date(2024, 3, 31)
        dates = [(day - timedelta(days=i)).isoformat() for i in range(89, -1, -1)]
        energy = [
            {
                'date': value,
                'expenditure_kcal': 2800,
                'expenditure_status': 'available',
                'coverage': 'full',
                'source': 'synthetic-model',
                'intake_kcal': None,
                'deficit_kcal': None,
                'is_projection': False,
                'usable': False,
            }
            for value in dates
        ]
        snapshot = {
            'sleep': {
                'daily': [
                    {
                        'date': value,
                        'duration_minutes': 420,
                        'score': 80,
                        'resting_hr': 55,
                        'hrv_ms': 50,
                        'body_battery': 75,
                    }
                    for value in dates
                ]
            },
            'performance': {
                'series': [
                    {'date': value, 'fitness': 50, 'fatigue': 60, 'form': -10, 'daily_load': 40, 'activity_count': 1}
                    for value in dates
                ]
            },
        }
        state = {
            'goals': [],
            'plans': [],
            'measurements': [{'date': value, 'weight_kg': 80} for value in dates],
            'checkins': [{'date': value, 'fatigue': 3, 'hunger': 4, 'pain': 1, 'sleep_hours': 7} for value in dates],
            'decisions': [],
        }
        prepared = prepare_personal(day, 90, snapshot, state, {'series': energy}, Diary())
        context = prepared['context']
        self.assertEqual(context['period']['from'], dates[0])
        self.assertEqual(metric(context['period_summaries']['registered_food'], 'kcal')['sum_registered'], 45000)
        self.assertEqual(metric(context['period_summaries']['sleep'], 'duration_minutes')['known_count'], 90)
        self.assertEqual(metric(context['period_summaries']['sleep'], 'duration_minutes')['mean'], 420)
        self.assertEqual(context['period_summaries']['food_coverage']['complete_nutrition_days'], 0)
        self.assertEqual(context['period_summaries']['food_coverage']['days_with_meals'], 90)
        self.assertFalse(context['selection']['all_daily_totals_included'])
        self.assertEqual(context['selection']['daily_rows']['energy']['total'], 90)
        text = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertLessEqual(len(text.encode()), MAX_CONTEXT_BYTES)
        self.assertLessEqual(_estimated_tokens(text), MAX_CONTEXT_TOKENS)

    def test_follow_up_only_uses_referenced_messages_from_its_conversation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Artifacts(Path(folder) / 'runtime', folder)
            first = answer(
                store,
                self.prepared(),
                'FIRST_CONVERSATION_MARKER',
                date(2024, 2, 1),
                manual_response='First synthetic answer for continuity.',
                conversation_id='conversation-one',
            )
            other = answer(
                store,
                self.prepared(),
                'UNRELATED_PRIVATE_MARKER',
                date(2024, 2, 1),
                manual_response='A separate synthetic answer.',
                conversation_id='conversation-two',
            )
            with patch('dashboard.assistant.request_text', return_value='Synthetic follow up') as infer:
                reply = answer(
                    store,
                    self.prepared(),
                    'Explain further',
                    date(2024, 2, 1),
                    conversation_id='conversation-one',
                    message_ids=[first['id']],
                )
                self.assertIn('FIRST_CONVERSATION_MARKER', infer.call_args.args[1])
                self.assertNotIn('UNRELATED_PRIVATE_MARKER', infer.call_args.args[1])
                self.assertEqual(reply['message_ids'], [first['id']])
                with self.assertRaisesRegex(ValueError, 'não pertence'):
                    answer(
                        store,
                        self.prepared(),
                        'Invalid reference',
                        date(2024, 2, 1),
                        conversation_id='conversation-one',
                        message_ids=[other['id']],
                    )
                self.assertEqual(infer.call_count, 1)

    def test_dense_calendar_month_summaries_cover_every_day(self):
        day = date(2024, 3, 31)
        dates = [(day - timedelta(days=i)).isoformat() for i in range(30, -1, -1)]
        energy = [
            {
                'date': value,
                'expenditure_kcal': 2800,
                'expenditure_status': 'available',
                'coverage': 'full',
                'source': 'synthetic-model',
                'intake_kcal': None,
                'deficit_kcal': None,
                'is_projection': False,
                'usable': False,
            }
            for value in dates
        ]
        snapshot = {
            'sleep': {
                'daily': [
                    {
                        'date': value,
                        'duration_minutes': 420,
                        'score': 80,
                        'resting_hr': 55,
                        'hrv_ms': 50,
                        'body_battery': 75,
                    }
                    for value in dates
                ]
            },
            'performance': {
                'series': [
                    {'date': value, 'fitness': 50, 'fatigue': 60, 'form': -10, 'daily_load': 40, 'activity_count': 1}
                    for value in dates
                ]
            },
        }
        state = {
            'goals': [],
            'plans': [],
            'measurements': [{'date': value, 'weight_kg': 80} for value in dates],
            'checkins': [{'date': value, 'fatigue': 3, 'hunger': 4, 'pain': 1, 'sleep_hours': 7} for value in dates],
            'decisions': [],
        }
        prepared = prepare_personal(day, 31, snapshot, state, {'series': energy}, Diary(), period='month')
        context = prepared['context']
        self.assertEqual(context['selection']['daily_rows']['food']['total'], 31)
        self.assertEqual(context['selection']['daily_rows']['energy']['total'], 31)
        self.assertEqual(metric(context['period_summaries']['registered_food'], 'kcal')['sum_registered'], 15500)
        self.assertEqual(context['period_summaries']['energy_by_status']['available']['observations'], 31)
        self.assertEqual(context['period']['from'], '2024-03-01')

    def test_medical_conversation_is_not_reused_after_opt_out(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Artifacts(Path(folder) / 'runtime', folder)
            first = answer(
                store,
                self.prepared(['profile', 'medical']),
                'MEDICAL_QUESTION_MARKER',
                date(2024, 2, 1),
                manual_response='MEDICAL_ANSWER_MARKER synthetic result.',
                conversation_id='conversation-one',
            )
            with patch('dashboard.assistant.request_text', return_value='Synthetic reply') as infer:
                reply = answer(
                    store,
                    self.prepared(),
                    'How is my training?',
                    date(2024, 2, 1),
                    conversation_id='conversation-one',
                    message_ids=[first['id']],
                )
            self.assertNotIn('MEDICAL_QUESTION_MARKER', infer.call_args.args[1])
            self.assertNotIn('MEDICAL_ANSWER_MARKER', infer.call_args.args[1])
            self.assertEqual(reply['withheld_medical_turns'], 1)

    def test_oversized_prompt_is_rejected_before_provider_call_or_save(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Artifacts(Path(folder) / 'runtime', folder)
            prepared = {**self.prepared(), 'prompt': '0123456789' * 2000}
            with patch('dashboard.assistant.request_text') as infer:
                with self.assertRaisesRegex(ValueError, 'excedem'):
                    answer(
                        store,
                        prepared,
                        'Synthetic question',
                        date(2024, 2, 1),
                        conversation_id='synthetic-conversation',
                    )
            infer.assert_not_called()
            self.assertEqual(store.read('assistant'), [])


if __name__ == '__main__':
    unittest.main()
