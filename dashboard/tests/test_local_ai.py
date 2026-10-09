"""Local inference routing and credentials safety with synthetic fixtures only."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import local_ai, nutrition, settings
from dashboard.provider_settings import ProviderSettings
from dashboard.settings import Settings


class LocalAiTests(unittest.TestCase):
    def test_local_selection_needs_no_api_key_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder, settings.override(runtime=Path(folder)):
            store = ProviderSettings(Path(folder))
            store.configure('ai', {'provider': 'ollama', 'local_model': 'gemma3:4b'})
            self.assertTrue(local_ai.configuration()['configured'])
            self.assertIsNone(store.credentials('ai').get('api_key'))
            ProviderSettings(Path(folder))
            self.assertEqual(local_ai.configuration()['provider'], 'ollama')
            store.configure('ai', enabled=False)
            self.assertFalse(local_ai.configuration()['configured'])

    def test_cloud_models_and_remote_hosts_rejected(self):
        for model in ['gemma3:cloud', 'model-cloud', '', 'bad name']:
            self.assertFalse(local_ai.valid_model(model))
        for host in ['https://ollama.com', 'http://example.com:11434', 'http://ollama:11434/remote']:
            with self.assertRaises(ValueError):
                local_ai.base_url(Settings.from_env({'OLLAMA_BASE_URL': host}))

    def test_food_uses_local_schema_and_never_paid_fallback(self):
        estimate = {
            'items': [{'name': 'Banana 100 g', 'kcal': 89, 'protein_g': 1.1, 'carbs_g': 23, 'fat_g': 0.3}],
            'notes': 'Estimativa sintética.',
        }
        response = {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(estimate)}}
        with tempfile.TemporaryDirectory() as folder:
            with settings.override(
                runtime=Path(folder),
                ai_provider='ollama',
                ai_enabled=True,
                ollama_model='gemma3:4b',
                openai_api_key='synthetic-unused',
            ):
                with (
                    patch(
                        'dashboard.local_ai.urlopen', return_value=io.BytesIO(json.dumps(response).encode())
                    ) as request,
                    patch('dashboard.nutrition.urlopen') as paid,
                ):
                    value = nutrition.estimate('Uma banana 100 g')
                    self.assertEqual(value['source'], 'ollama')
                    self.assertEqual(value['items'][0]['kcal'], 89)
                    body = json.loads(request.call_args.args[0].data)
                    self.assertIsInstance(body['format'], dict)
                    self.assertFalse(body['think'])
                    self.assertEqual(request.call_args.args[0].full_url, 'http://ollama:11434/api/chat')
                    self.assertIsNone(request.call_args.args[0].get_header('Authorization'))
                    paid.assert_not_called()
                with (
                    patch('dashboard.local_ai.urlopen', side_effect=TimeoutError),
                    patch('dashboard.nutrition.urlopen') as paid,
                ):
                    with self.assertRaisesRegex(RuntimeError, 'Ollama local'):
                        nutrition.estimate('Uma banana 100 g')
                    paid.assert_not_called()

    def test_photo_is_attached_locally_without_external_url(self):
        content: list = [
            {
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': 'Foto sintética'},
                    {'type': 'input_image', 'image_url': 'data:image/png;base64,c3ludGhldGlj'},
                ],
            }
        ]
        value = local_ai.messages('Estime', content)
        self.assertEqual(value[1]['images'], ['c3ludGhldGlj'])
        content[0]['content'][1]['image_url'] = 'https://example.com/private.png'
        with self.assertRaises(ValueError):
            local_ai.messages('Estime', content)

    def test_incomplete_local_response_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            with (
                settings.override(runtime=Path(folder), ai_provider='ollama', ai_enabled=True),
                patch(
                    'dashboard.local_ai.urlopen',
                    return_value=io.BytesIO(b'{"done":true,"done_reason":"length","message":{"content":"{}"}}'),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, 'não concluiu'):
                    local_ai.request_text('Test', 'Synthetic')
