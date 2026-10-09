"""Versioned PostgreSQL repository and lossless legacy calculation adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATHLETE_ID = uuid.UUID("9dcb4c42-e857-4279-b06e-7e29d9c714d8")
LOCK_ID = 1730962174
CURRENT: ContextVar[dict | None] = ContextVar("athlete_repository", default=None)
REVISION: ContextVar[uuid.UUID | None] = ContextVar("athlete_revision", default=None)


class RevisionCache:
    """In-memory cache scoped to a single revision; callers must copy before mutating."""

    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._value = None
        self._parsed_key = None
        self._parsed = {}

    @staticmethod
    def _enabled():
        from dashboard.settings import current

        return current().revision_cache

    def get(self, key, loader):
        if not self._enabled():
            return loader()
        with self._lock:
            if self._key != key:
                self._key, self._value = key, loader()
            return self._value

    def parsed(self, key, path, raw):
        if not self._enabled():
            return json.loads(raw.decode("utf-8-sig"))
        with self._lock:
            if self._parsed_key != key:
                self._parsed_key, self._parsed = key, {}
            if path not in self._parsed:
                self._parsed[path] = json.loads(raw.decode("utf-8-sig"))
            return self._parsed[path]

    def invalidate(self):
        with self._lock:
            self._key = self._value = self._parsed_key = None
            self._parsed = {}


FILES_CACHE = RevisionCache()
SNAPSHOT_CACHE = RevisionCache()


def datasets_in_postgres(root=ROOT):
    return Path(root).resolve() == ROOT.resolve()


_database_override: str | None = None


@contextmanager
def use_database(name):
    global _database_override
    previous = _database_override
    _database_override = name
    try:
        yield
    finally:
        _database_override = previous


def connect(**kwargs):
    import psycopg

    if _database_override is not None:
        kwargs.setdefault("dbname", _database_override)

    return psycopg.connect(connect_timeout=10, **kwargs)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def read_files(root):
    paths = sorted((root / "data").glob("*.json")) + sorted((root / "analysis").rglob("*.json"))
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in paths}


def validate_path(path):
    value = Path(path)
    if (
        value.is_absolute()
        or ".." in value.parts
        or value.parts[0] not in {"data", "analysis"}
        or value.suffix != ".json"
    ):
        raise ValueError("Invalid dataset path")


def contents_digest(files):
    digest = hashlib.sha256()
    for path, raw in sorted(files.items()):
        validate_path(path)
        json.loads(raw.decode("utf-8-sig"))
        digest.update(path.encode() + b"\0" + hashlib.sha256(raw).digest())
    return digest.hexdigest()


def validate_datasets(values):
    garmin = set()
    for row in values.get("data/training_history.json") or []:
        external = row.get("garmin_activity_id")
        if external is None:
            continue
        if str(external) in garmin:
            raise RuntimeError("Duplicate Garmin activity ID requires review")
        garmin.add(str(external))
    hevy_rows = values.get("data/hevy_workouts.json") or []
    if len({str(row["hevy_workout_id"]) for row in hevy_rows}) != len(hevy_rows):
        raise RuntimeError("Duplicate Hevy workout ID requires review")


def migrate():
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        conn.execute("CREATE SCHEMA IF NOT EXISTS athlete")
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            has_table = conn.execute("SELECT to_regclass('athlete.schema_migrations')").fetchone()[0]
            prior = (
                conn.execute("SELECT checksum FROM athlete.schema_migrations WHERE version=%s", (path.name,)).fetchone()
                if has_table
                else None
            )
            if prior:
                if prior[0] != checksum:
                    raise RuntimeError("Applied migration checksum changed")
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO athlete.schema_migrations(version,checksum) VALUES(%s,%s)", (path.name, checksum))


class PostgresRepository:
    def active(self):
        with connect() as conn:
            row = conn.execute("SELECT active_revision FROM athlete.state WHERE singleton").fetchone()
            return row[0] if row else None

    def files(self, revision=None):
        with connect() as conn:
            if revision is None:
                revision = conn.execute("SELECT active_revision FROM athlete.state WHERE singleton").fetchone()[0]
                if revision is None:
                    raise RuntimeError("PostgreSQL has not been initialized with athlete data")
                return revision, FILES_CACHE.get(revision, lambda: self._load_files(conn, revision))
            return revision, self._load_files(conn, revision)

    @staticmethod
    def _load_files(conn, revision):
        rows = conn.execute(
            "SELECT d.path,b.original_bytes FROM athlete.datasets d JOIN athlete.dataset_blobs b ON b.digest=d.digest WHERE d.revision_id=%s",
            (revision,),
        )
        return {path: bytes(raw) for path, raw in rows}

    def export(self, target, revision=None):
        revision, files = self.files(revision)
        for path, raw in files.items():
            validate_path(path)
            dest = target / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        return revision

    def publish(self, files, *, reason, expected=None, warnings=None, documents=None, report=None):
        from psycopg.types.json import Jsonb

        digest = contents_digest(files)
        if documents is not None:
            digest = hashlib.sha256((digest + canonical(documents)).encode()).hexdigest()
        revision = uuid.uuid5(ATHLETE_ID, digest)
        values = {path: json.loads(raw.decode("utf-8-sig")) for path, raw in files.items()}
        validate_datasets(values)
        with connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            current = conn.execute("SELECT active_revision FROM athlete.state WHERE singleton FOR UPDATE").fetchone()[0]
            if current != expected:
                raise RuntimeError("Database changed during import; retry without overwriting newer data")
            if not conn.execute("SELECT id FROM athlete.revisions WHERE id=%s", (revision,)).fetchone():
                conn.execute(
                    "INSERT INTO athlete.revisions(id,athlete_id,digest,reason,warnings) VALUES(%s,%s,%s,%s,%s)",
                    (revision, ATHLETE_ID, digest, reason, Jsonb(warnings or [])),
                )
                for path, raw in files.items():
                    key = hashlib.sha256(raw).hexdigest()
                    conn.execute(
                        "INSERT INTO athlete.dataset_blobs VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (key, Jsonb(values[path]), raw),
                    )
                    conn.execute("INSERT INTO athlete.datasets VALUES(%s,%s,%s)", (revision, path, key))
            for path, info in (documents or {}).items():
                conn.execute(
                    "INSERT INTO athlete.documents VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (revision, path, info["sha256"], info["bytes"]),
                )
            if report:
                conn.execute(
                    "INSERT INTO athlete.reports(id,revision_id,metadata) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (report["id"], revision, Jsonb(report)),
                )
            conn.execute("UPDATE athlete.state SET active_revision=%s WHERE singleton", (revision,))
        FILES_CACHE.invalidate()
        return revision

    def counts(self, revision=None):
        from psycopg import sql

        revision = revision or self.active()
        tables = (
            "datasets",
            "documents",
            "reports",
        )
        with connect() as conn:
            return {
                name: conn.execute(
                    sql.SQL("SELECT count(*) FROM athlete.{} WHERE revision_id=%s").format(sql.Identifier(name)),
                    (revision,),
                ).fetchone()[0]
                for name in tables
            }


@contextmanager
def repository_context(root):
    if datasets_in_postgres(root):
        revision, files = PostgresRepository().files()
        token = CURRENT.set(files)
        revision_token = REVISION.set(revision)
        try:
            yield
        finally:
            CURRENT.reset(token)
            REVISION.reset(revision_token)
    else:
        yield


def revision_metadata():
    revision = REVISION.get()
    if revision is None:
        return None
    with connect() as conn:
        row = conn.execute("SELECT warnings FROM athlete.revisions WHERE id=%s", (revision,)).fetchone()
    return {"backend": "postgres", "revision": str(revision), "warnings": row[0]}


def read_dataset(root, path, default=None):
    files = CURRENT.get()
    revision = REVISION.get()
    if files is None and datasets_in_postgres(root):
        revision, files = PostgresRepository().files()
    if files is not None:
        raw = files.get(path)
        if raw is None:
            return default
        if revision is not None:
            return copy.deepcopy(FILES_CACHE.parsed(revision, path, raw))
        return json.loads(raw.decode("utf-8-sig"))
    local = Path(root) / path
    raw = local.read_bytes() if local.exists() else None
    return json.loads(raw.decode("utf-8-sig")) if raw is not None else default


def dataset_bytes(root, path):
    files = CURRENT.get()
    if files is not None:
        return files.get(path)
    local = Path(root) / path
    return local.read_bytes() if local.exists() else None


class HybridRow(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: HybridRow(zip(names, values))


@contextmanager
def operational_db():
    from psycopg import sql

    from dashboard.settings import current

    schema = current().operations_schema
    with connect(row_factory=row_factory) as conn:
        conn.execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(schema)))
        yield conn


def operational_lock(conn):
    """Serialize writers on a dedicated advisory lock inside the transaction."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID + 1,))


def document_manifest(root):
    from dashboard.backup import file_hash

    return {
        p.relative_to(root).as_posix(): {"sha256": file_hash(p), "bytes": p.stat().st_size}
        for p in sorted((root / "activities").rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
