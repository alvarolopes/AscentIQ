"""Private, versioned supporting records and allowlisted document storage."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dashboard.repository import operational_db, postgres_enabled

_UPLOAD_LOCK = threading.RLock()


class Artifacts:
    def __init__(self, runtime, root):
        self.runtime, self.root = Path(runtime), Path(root)
        self.folder = self.runtime / 'personal-documents'
        if self.folder.is_symlink():
            raise ValueError('Pasta de documentos não pode apontar para outro diretório.')
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self.folder.resolve().is_relative_to(self.runtime.resolve()):
            raise ValueError('Pasta de documentos fora do ambiente privado.')
        if not postgres_enabled(root):
            with self._db() as conn:
                conn.execute(
                    'CREATE TABLE IF NOT EXISTS personal_artifacts (id TEXT PRIMARY KEY,payload TEXT NOT NULL)'
                )

    def _db(self):
        return operational_db(self.runtime, 'artifacts', self.root)

    def read(self, kind):
        with self._db() as conn:
            row = conn.execute('SELECT payload FROM personal_artifacts WHERE id=?', (kind,)).fetchone()
            return json.loads(row[0]) if row else []

    def save(self, kind, record, *, if_absent=False):
        if not isinstance(record, dict):
            raise ValueError('O registro deve ser um objeto.')
        with self._db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT payload FROM personal_artifacts WHERE id=?', (kind,)).fetchone()
            records = json.loads(row[0]) if row else []
            record_id = str(record.get('id') or uuid.uuid4())
            previous = next((x for x in records if x['id'] == record_id), None)
            if previous and if_absent:
                return previous
            record = {**(previous or {}), **record, 'id': record_id}
            comparable = lambda value: {k: v for k, v in value.items() if k not in ('created_at', 'updated_at')}
            if previous and comparable(previous) == comparable(record):
                return previous
            stamp = datetime.now(UTC).isoformat()
            record['created_at'] = (previous or {}).get('created_at') or record.get('created_at') or stamp
            record['updated_at'] = stamp
            if previous:
                revision_id = kind + ':history:' + uuid.uuid4().hex
                conn.execute(
                    'INSERT INTO personal_artifacts(id,payload) VALUES(?,?)',
                    (revision_id, json.dumps(previous, ensure_ascii=False, allow_nan=False)),
                )
            records = [x for x in records if x['id'] != record['id']] + [record]
            conn.execute(
                'INSERT INTO personal_artifacts(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                (kind, json.dumps(records, ensure_ascii=False, allow_nan=False)),
            )
        return record

    def remove(self, kind, record_id):
        with self._db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT payload FROM personal_artifacts WHERE id=?', (kind,)).fetchone()
            records = json.loads(row[0]) if row else []
            removed = [x for x in records if x['id'] == record_id]
            if removed:
                conn.execute(
                    'INSERT INTO personal_artifacts(id,payload) VALUES(?,?)',
                    (kind + ':deleted:' + uuid.uuid4().hex, json.dumps(removed)),
                )
                conn.execute(
                    'UPDATE personal_artifacts SET payload=? WHERE id=?',
                    (json.dumps([x for x in records if x['id'] != record_id]), kind),
                )
        return self.read(kind)

    def export(self):
        with self._db() as conn:
            return {row[0]: json.loads(row[1]) for row in conn.execute('SELECT id,payload FROM personal_artifacts')}

    def upload_document(self, filename, content, label, day):
        with _UPLOAD_LOCK:
            return self._upload_document(filename, content, label, day)

    def _upload_document(self, filename, content, label, day):
        if not isinstance(filename, str) or len(filename) > 200:
            raise ValueError('Nome de documento inválido.')
        suffix = Path(filename).suffix.lower()
        if suffix not in ('.pdf', '.txt', '.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Use PDF, texto, JPEG, PNG ou WebP.')
        try:
            raw = base64.b64decode(content, validate=True)
        except Exception as error:
            raise ValueError('Conteúdo do documento inválido.') from error
        if not 1 <= len(raw) <= 12 * 1024 * 1024:
            raise ValueError('O documento deve ter até 12 MB.')
        if suffix == '.pdf' and not raw.startswith(b'%PDF-'):
            raise ValueError('O arquivo não é um PDF válido.')
        if suffix in ('.png', '.jpg', '.jpeg', '.webp'):
            valid = (
                suffix in ('.jpg', '.jpeg')
                and raw.startswith(b'\xff\xd8')
                or suffix == '.png'
                and raw.startswith(b'\x89PNG\r\n\x1a\n')
                or suffix == '.webp'
                and raw.startswith(b'RIFF')
                and raw[8:12] == b'WEBP'
            )
            if not valid:
                raise ValueError('O conteúdo não corresponde ao formato da imagem.')
        digest = hashlib.sha256(raw).hexdigest()
        path = self.folder / (digest + suffix)
        text = ''
        if suffix == '.txt':
            text = raw.decode('utf-8-sig')
        elif suffix == '.pdf':
            from pypdf import PdfReader

            try:
                reader = PdfReader(io.BytesIO(raw))
                if reader.is_encrypted:
                    raise ValueError('Envie um PDF sem senha.')
                if len(reader.pages) > 100:
                    raise ValueError('Use documentos com até 100 páginas.')
                text = '\n'.join(
                    f'Página {i + 1}:\n' + (page.extract_text() or '') for i, page in enumerate(reader.pages)
                )
            except ValueError:
                raise
            except Exception as error:
                raise ValueError(
                    'Não foi possível ler o PDF. Envie um arquivo válido ou registre uma referência em texto.'
                ) from error
        # Parse and validate first. A rejected upload must not leave private
        # orphan files, and concurrent writes must not share a temporary name.
        if path.is_symlink():
            raise ValueError('Arquivo de documento não pode ser um vínculo externo.')
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('O documento armazenado falhou na verificação de integridade.')
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=digest + '-', suffix='.tmp', dir=self.folder)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        previous = next((x for x in self.read('documents') if x.get('sha256') == digest), None)
        if previous:
            return previous
        return self.save(
            'documents',
            {
                'id': digest,
                'sha256': digest,
                'filename': Path(filename.replace('\\', '/')).name,
                'stored_name': path.name,
                'label': str(label or filename)[:200],
                'date': day,
                'bytes': len(raw),
                'text': text[:120000],
                'observations': [],
                'reviewed': False,
                'source': 'uploaded',
                'extraction': 'local_text' if text else 'not_extracted',
            },
            if_absent=True,
        )

    def document_path(self, document_id):
        record = next((x for x in self.read('documents') if x['id'] == document_id), None)
        if record is None:
            return None
        path = self.folder / record['stored_name']
        return (
            path
            if path.is_file() and not path.is_symlink() and path.resolve().parent == self.folder.resolve()
            else None
        )
