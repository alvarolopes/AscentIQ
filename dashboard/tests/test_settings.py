"""Settings is immutable, loaded once, and keeps credentials off os.environ."""

import dataclasses
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard import settings as settings_module
from dashboard.provider_settings import ProviderSettings
from dashboard.settings import Settings
from dashboard.tests import pg


class SettingsTests(unittest.TestCase):
    def test_from_env_reads_once_and_is_immutable(self):
        env = {'OLLAMA_MODEL': 'synthetic-model'}
        instance = Settings.from_env(env)
        env['OLLAMA_MODEL'] = 'changed'
        self.assertEqual(instance.ollama_model, 'synthetic-model')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            instance.ollama_model = 'other'  # type: ignore[misc]  # verifica frozen

    def test_override_restores_previous(self):
        before = settings_module.current()
        with settings_module.override(ai_provider='ollama') as inside:
            self.assertEqual(inside.ai_provider, 'ollama')
            self.assertEqual(settings_module.current().ai_provider, 'ollama')
        self.assertIs(settings_module.current(), before)

    def test_defaults_match_previous_behaviour(self):
        instance = Settings.from_env({})
        self.assertEqual(instance.ai_provider, 'openai')
        self.assertEqual(instance.openai_model, 'gpt-5')
        self.assertEqual(instance.ollama_model, 'qwen3.5:4b')
        self.assertEqual(instance.ollama_base_url, 'http://ollama:11434')
        self.assertEqual(instance.timezone, 'America/Sao_Paulo')
        self.assertTrue(instance.schedule_enabled)
        self.assertTrue(instance.sleep_schedule_enabled)
        self.assertFalse(instance.secure_cookies)
        self.assertTrue(instance.revision_cache)
        self.assertEqual(instance.operations_schema, 'operations')
        self.assertEqual(instance.sync_start_date, date(2024, 1, 1))


class ProviderIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def test_provider_credentials_never_reach_process_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            providers = ProviderSettings(Path(folder))
            providers.configure('hevy', {'api_key': 'synthetic'})
            self.assertIsNone(os.environ.get('HEVY_API_KEY'))
            self.assertEqual(providers.credentials('hevy'), {'api_key': 'synthetic'})
            self.assertNotIn('synthetic', json.dumps(providers.status()))
            self.assertNotIn(b'synthetic', providers.path.read_bytes())

    def test_environment_credentials_are_used_without_saved_configuration(self):
        env = {
            'GARMIN_EMAIL': 'synthetic@example.test',
            'GARMIN_PASSWORD': 'synthetic-password',
            'HEVY_API_KEY': 'synthetic-key',
        }
        instance = Settings.from_env(env)
        env['HEVY_API_KEY'] = 'changed-after-loading'
        before = dict(os.environ)
        with tempfile.TemporaryDirectory() as folder:
            providers = ProviderSettings(Path(folder))
            self.assertEqual(
                providers.credentials('garmin', instance),
                {'email': 'synthetic@example.test', 'password': 'synthetic-password'},
            )
            self.assertEqual(providers.credentials('hevy', instance), {'api_key': 'synthetic-key'})
            status = {item['id']: item for item in providers.status(instance)}
            self.assertTrue(status['garmin']['configured'])
            self.assertTrue(status['hevy']['configured'])
            self.assertNotIn('synthetic-key', json.dumps(status))
            self.assertFalse(providers.path.exists())
        self.assertEqual(dict(os.environ), before)

    def test_saved_credentials_and_disconnect_override_environment(self):
        instance = Settings.from_env({'HEVY_API_KEY': 'synthetic-environment-key'})
        with tempfile.TemporaryDirectory() as folder:
            providers = ProviderSettings(Path(folder))
            providers.configure('hevy', {'api_key': 'synthetic-ui-key'}, settings=instance)
            self.assertEqual(providers.credentials('hevy', instance), {'api_key': 'synthetic-ui-key'})
            providers.configure('hevy', enabled=False, settings=instance)
            self.assertEqual(providers.credentials('hevy', instance), {})
            status = next(item for item in providers.status(instance) if item['id'] == 'hevy')
            self.assertFalse(status['configured'])
            self.assertFalse(status['enabled'])

    def test_environment_credentials_reach_sync_child_without_environment_writes(self):
        from dashboard.pipeline import sync_sources

        instance = Settings.from_env({'HEVY_API_KEY': 'synthetic-environment-key'})
        before = dict(os.environ)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            providers = ProviderSettings(root / 'runtime')
            with patch('dashboard.pipeline.run_script') as run:
                sync_sources(
                    root,
                    sources=('hevy',),
                    credentials={'hevy': providers.credentials('hevy', instance)},
                    enabled={'hevy': providers.enabled('hevy')},
                    settings=instance,
                )
            fetch = next(call for call in run.call_args_list if call.args[0] == 'fetch_hevy_workouts.py')
            self.assertEqual(fetch.kwargs['environment']['HEVY_API_KEY'], 'synthetic-environment-key')
        self.assertEqual(dict(os.environ), before)

    def test_sync_sources_passes_credentials_only_to_child(self):
        from dashboard.pipeline import sync_sources

        captured = []

        def stub(name, *arguments, **kwargs):
            captured.append((name, kwargs.get('environment')))
            (Path(kwargs.get('root') or '') / 'data').mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            (root / 'data' / 'training_history.json').write_text('[]')
            with patch('dashboard.pipeline.run_script', side_effect=stub):
                warnings = sync_sources(
                    root,
                    sources=('hevy', 'garmin'),
                    credentials={'hevy': {'api_key': 'synthetic-hevy'}, 'garmin': {}},
                    enabled={'hevy': True, 'garmin': False},
                )
        child = next(env for name, env in captured if name == 'fetch_hevy_workouts.py')
        assert child is not None
        self.assertEqual(child['HEVY_API_KEY'], 'synthetic-hevy')
        self.assertIsNone(os.environ.get('HEVY_API_KEY'))
        self.assertIn('Integração garmin desconectada; histórico preservado.', warnings)

    def test_schedule_follows_preferences_not_environment(self):
        from dashboard.jobs import JobManager, schedule_slot
        from dashboard.settings import default_tz

        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / 'runtime'
            off = JobManager(
                Settings.from_env({}),
                runtime,
                Path(folder),
                preferences=lambda: {'weekly_sync': False},
                providers=None,
            )
            self.assertTrue(off.settings.schedule_enabled)
            future = schedule_slot(datetime.now(default_tz())) + timedelta(days=7, minutes=1)
            off.tick_schedule(future)
            self.assertEqual(off.list(), [])
            on = JobManager(
                Settings.from_env({}),
                runtime,
                Path(folder),
                preferences=lambda: {'weekly_sync': True},
                providers=None,
            )
            on.tick_schedule(future)
            self.assertEqual(len(on.list()), 1)

    def test_ai_configuration_prefers_ui_over_environment(self):
        instance = Settings.from_env({'ASCENTIQ_AI_PROVIDER': 'openai'})
        with tempfile.TemporaryDirectory() as folder:
            providers = ProviderSettings(Path(folder))
            providers.configure('ai', {'provider': 'ollama', 'local_model': 'qwen3.5:4b'}, settings=instance)
            ai = providers.ai_configuration(instance)
            self.assertEqual(ai.provider, 'ollama')
            self.assertTrue(ai.configured)
            self.assertTrue(ai.local)

    def test_no_environment_writes_in_dashboard(self):
        import re

        sources = Path(__file__).resolve().parents[1]
        pattern = re.compile(r'os\.environ\[[^]]+\]\s*=|os\.environ\.(update|setdefault|pop)')
        for path in sorted(sources.glob('*.py')):
            if path.name in {'database_cli.py', 'settings.py'}:
                continue
            self.assertNotRegex(path.read_text(encoding='utf-8'), pattern, path.name)


if __name__ == '__main__':
    unittest.main()
