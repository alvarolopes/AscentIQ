"""Credentials configured in the private UI, encrypted at rest and never returned."""

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dashboard.settings import Settings, current

FIELDS = {
    'garmin': {'email': 'GARMIN_EMAIL', 'password': 'GARMIN_PASSWORD'},
    'hevy': {'api_key': 'HEVY_API_KEY'},
    'ai': {
        'provider': 'ASCENTIQ_AI_PROVIDER',
        'api_key': 'OPENAI_API_KEY',
        'model': 'OPENAI_MODEL',
        'local_model': 'OLLAMA_MODEL',
    },
}
_LOCK = threading.RLock()


@dataclass(frozen=True)
class AIConfiguration:
    provider: str
    model: str
    enabled: bool
    local: bool
    configured: bool
    api_key: str | None = None


def default_ai(settings: Settings | None = None) -> AIConfiguration:
    settings = settings or current()
    return ProviderSettings(settings.runtime).ai_configuration(settings)


class ProviderSettings:
    def __init__(self, runtime):
        self.folder = Path(runtime) / 'connections'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.key = self.folder / 'credentials.key'
        self.path = self.folder / 'credentials.enc'

    def _read(self):
        if not self.path.exists():
            return {}
        raw = self.path.read_bytes()
        return json.loads(AESGCM(self.key.read_bytes()).decrypt(raw[:12], raw[12:], b'ascentiq-connections-v1'))

    def credentials(self, provider, settings=None):
        values = self._read()
        if provider in values:
            saved = values[provider]
            return dict(saved.get('credentials', {})) if saved.get('enabled', True) else {}
        settings = settings or current()
        fallback = {
            'garmin': {'email': settings.garmin_email, 'password': settings.garmin_password},
            'hevy': {'api_key': settings.hevy_api_key},
        }.get(provider, {})
        return {key: value for key, value in fallback.items() if value}

    def enabled(self, provider):
        return bool(self._read().get(provider, {}).get('enabled', True))

    def ai_configuration(self, settings=None):
        from dashboard.local_ai import valid_model

        settings = settings or current()
        saved = self._read().get('ai', {})
        credentials = saved.get('credentials', {}) if saved.get('enabled', True) else {}
        enabled = bool(saved.get('enabled', True) and settings.ai_enabled)
        provider = credentials.get('provider') or settings.ai_provider
        local = provider == 'ollama'
        if local:
            model = credentials.get('local_model') or settings.ollama_model
            configured = enabled and valid_model(model)
            api_key = None
        else:
            model = credentials.get('model') or settings.openai_model
            api_key = credentials.get('api_key') or settings.openai_api_key
            configured = enabled and provider == 'openai' and bool(api_key)
        return AIConfiguration(provider, model, enabled, local, configured, api_key)

    def _env_fallback(self, provider, key, settings):
        if provider != 'ai':
            return None
        return {
            'provider': settings.ai_provider,
            'api_key': settings.openai_api_key,
            'model': settings.openai_model,
            'local_model': settings.ollama_model,
        }.get(key)

    def configure(self, provider, credentials=None, *, enabled=True, settings=None):
        with _LOCK:
            return self._configure(provider, credentials, enabled=enabled, settings=settings or current())

    def _configure(self, provider, credentials=None, *, enabled=True, settings):
        if provider not in FIELDS:
            raise ValueError('Integração desconhecida.')
        if not isinstance(enabled, bool):
            raise ValueError('Estado da integração deve ser verdadeiro ou falso.')
        if credentials is None:
            credentials = {}
        if not isinstance(credentials, dict):
            raise ValueError('Credenciais devem ser um objeto com os campos permitidos.')
        if set(credentials) - set(FIELDS[provider]):
            raise ValueError('Campo de credencial inválido.')
        if any(not isinstance(x, str) or len(x) > 500 for x in credentials.values()):
            raise ValueError('Credencial inválida.')
        values = self._read()
        previous = values.get(provider, {}).get('credentials', {})
        merged = {**previous, **{k: v.strip() for k, v in credentials.items() if v.strip()}}
        required = [key for key in FIELDS[provider] if key not in {'model', 'local_model', 'provider'}]
        if provider == 'ai':
            selected = merged.get('provider') or settings.ai_provider
            if selected not in {'ollama', 'openai'}:
                raise ValueError('Selecione Ollama local ou OpenAI.')
            if merged.get('local_model'):
                from dashboard.local_ai import valid_model

                if not valid_model(merged['local_model']):
                    raise ValueError('Use um modelo local instalado; modelos cloud não são permitidos.')
            if selected == 'ollama':
                required = []
        if enabled and any(not merged.get(k) and not self._env_fallback(provider, k, settings) for k in required):
            raise ValueError('Informe os dados de acesso da integração.')
        values[provider] = {'enabled': bool(enabled), 'credentials': merged if enabled else {}}
        if not self.key.exists():
            fd = os.open(self.key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(os.urandom(32))
        nonce = os.urandom(12)
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(
            nonce
            + AESGCM(self.key.read_bytes()).encrypt(nonce, json.dumps(values).encode(), b'ascentiq-connections-v1')
        )
        temp.chmod(0o600)
        temp.replace(self.path)
        return self.status(settings)

    def status(self, settings=None):
        settings = settings or current()
        ai = self.ai_configuration(settings)
        return [
            {
                'id': provider,
                'name': {'garmin': 'Garmin Connect', 'hevy': 'Hevy', 'ai': 'Inteligência artificial'}[provider],
                'configured': ai.configured
                if provider == 'ai'
                else all(self.credentials(provider, settings).get(key) for key in fields),
                'enabled': ai.enabled if provider == 'ai' else self.enabled(provider),
                **({'provider': ai.provider, 'model': ai.model, 'local': ai.local} if provider == 'ai' else {}),
                'fields': list(fields),
                'mode': 'read_only' if provider != 'ai' else 'on_request',
            }
            for provider, fields in FIELDS.items()
        ]
