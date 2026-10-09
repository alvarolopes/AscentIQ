import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.server import create_app
from dashboard.settings import Settings
from dashboard.tests import pg


class ExportArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def test_explicit_attachments_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            runtime = root / 'runtime'
            headers = {'X-AscentIQ-Request': '1'}
            app_settings = Settings.from_env(
                {
                    **os.environ,
                    'DASHBOARD_USERNAME': 'tester',
                    'DASHBOARD_PASSWORD': 'synthetic',
                    'DASHBOARD_SCHEDULE_ENABLED': 'false',
                    'DASHBOARD_SLEEP_SCHEDULE_ENABLED': 'false',
                }
            )
            with TestClient(create_app(runtime, root, app_settings)) as client:
                client.post('/api/auth/login', json={'username': 'tester', 'password': 'synthetic'}, headers=headers)
                document = client.post(
                    '/api/documents',
                    json={
                        'filename': 'synthetic.txt',
                        'date': '2026-10-01',
                        'content': base64.b64encode(b'SYNTHETIC ATTACHMENT').decode(),
                    },
                    headers=headers,
                ).json()
                (runtime / 'auth-private.txt').write_text('NEVER-EXPORTED-SECRET')
                default = client.get('/api/export/archive')
                self.assertEqual(default.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(default.content)) as archive:
                    self.assertEqual(set(archive.namelist()), {'context.json', 'manifest.json'})
                selected = client.get('/api/export/archive?include_documents=true')
                with zipfile.ZipFile(io.BytesIO(selected.content)) as archive:
                    names = archive.namelist()
                    self.assertTrue(any(name.startswith('documents/') for name in names))
                    combined = b''.join(archive.read(name) for name in names)
                    self.assertNotIn(b'NEVER-EXPORTED-SECRET', combined)
                    self.assertIn(b'SYNTHETIC ATTACHMENT', combined)
                    exported = json.loads(archive.read('context.json'))
                    self.assertIn('personal_revisions', exported)
                    self.assertTrue(exported['artifacts']['documents'][0]['id'] == document['id'])
                self.assertEqual(list((runtime / 'exports').glob('*.zip')), [])
