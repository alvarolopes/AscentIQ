"""Credentials configured in the private UI, encrypted at rest and never returned."""

import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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


class ProviderSettings:
    def __init__(self, runtime):
        self.folder = Path(runtime) / 'connections'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.key = self.folder / 'credentials.key'
        self.path = self.folder / 'credentials.enc'
        self.apply()

    def _read(self):
        if not self.path.exists():
            return {}
        raw = self.path.read_bytes()
        return json.loads(AESGCM(self.key.read_bytes()).decrypt(raw[:12], raw[12:], b'ascentiq-connections-v1'))

    def configure(self, provider, credentials=None, *, enabled=True):
        with _LOCK:
            return self._configure(provider, credentials, enabled=enabled)

    def _configure(self, provider, credentials=None, *, enabled=True):
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
            selected = merged.get('provider', os.environ.get('ASCENTIQ_AI_PROVIDER', 'openai'))
            if selected not in {'ollama', 'openai'}:
                raise ValueError('Selecione Ollama local ou OpenAI.')
            if merged.get('local_model'):
                from dashboard.local_ai import valid_model

                if not valid_model(merged['local_model']):
                    raise ValueError('Use um modelo local instalado; modelos cloud não são permitidos.')
            if selected == 'ollama':
                required = []
        if enabled and any(not merged.get(k) and not os.environ.get(FIELDS[provider][k]) for k in required):
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
        self.apply()
        return self.status()

    def apply(self):
        for provider, config in self._read().items():
            os.environ['ASCENTIQ_' + provider.upper() + '_ENABLED'] = str(config['enabled']).lower()
            for key, env in FIELDS[provider].items():
                if not config['enabled']:
                    os.environ[env] = ''
                elif config['credentials'].get(key):
                    os.environ[env] = config['credentials'][key]

    def status(self):
        from dashboard.local_ai import configuration

        ai = configuration()
        return [
            {
                'id': provider,
                'name': {'garmin': 'Garmin Connect', 'hevy': 'Hevy', 'ai': 'Inteligência artificial'}[provider],
                'configured': ai['configured']
                if provider == 'ai'
                else all(bool(os.environ.get(env)) for key, env in fields.items() if key != 'model'),
                'enabled': os.environ.get('ASCENTIQ_' + provider.upper() + '_ENABLED', 'true') == 'true',
                **(
                    {'provider': ai['provider'], 'model': ai['model'], 'local': ai['local']} if provider == 'ai' else {}
                ),
                'fields': list(fields),
                'mode': 'read_only' if provider != 'ai' else 'on_request',
            }
            for provider, fields in FIELDS.items()
        ]
