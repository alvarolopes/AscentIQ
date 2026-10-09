"""Versioned PostgreSQL repository and lossless legacy calculation adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
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
        return os.environ.get("ASCENTIQ_REVISION_CACHE") != "false"

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


def postgres_enabled(root=ROOT):
    return Path(root).resolve() == ROOT.resolve() and os.environ.get("DATABASE_BACKEND", "json") == "postgres"


def connect(**kwargs):
    import psycopg

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


def number(value):
    return None if value is None or value == "" else float(value)


def duration(row):
    if row.get("duration_seconds") is not None:
        return number(row["duration_seconds"])
    if row.get("elapsed_time") is None:
        return None
    seconds = 0.0
    for part in str(row["elapsed_time"]).split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def day(value):
    return date.fromisoformat(str(value)[:10]) if value else None


def identity(row, namespace="activity", ordinal=None):
    key = (
        row.get("garmin_activity_id") or row.get("activity_key") or row.get("strava_activity_id") or row.get("filename")
    )
    if key is None:
        key = canonical([row.get("date_time") or row.get("date"), row.get("type"), row.get("name"), ordinal])
    return uuid.uuid5(ATHLETE_ID, namespace + ":" + str(key))


def migrate():
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        conn.execute("CREATE SCHEMA IF NOT EXISTS athlete")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS athlete.schema_migrations(version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())"
        )
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            prior = conn.execute(
                "SELECT checksum FROM athlete.schema_migrations WHERE version=%s", (path.name,)
            ).fetchone()
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

    def publish(self, files, *, reason, expected=None, warnings=None, snapshot=None, documents=None, report=None):
        from psycopg.types.json import Jsonb

        digest = contents_digest(files)
        if documents is not None:
            digest = hashlib.sha256((digest + canonical(documents)).encode()).hexdigest()
        revision = uuid.uuid5(ATHLETE_ID, digest)
        values = {path: json.loads(raw.decode("utf-8-sig")) for path, raw in files.items()}
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
                self._project(conn, revision, values)
            for path, info in (documents or {}).items():
                conn.execute(
                    "INSERT INTO athlete.documents VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (revision, path, info["sha256"], info["bytes"]),
                )
            if snapshot:
                for row in snapshot["performance"]["series"]:
                    conn.execute(
                        "INSERT INTO athlete.daily_metrics VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (
                            revision,
                            day(row["date"]),
                            snapshot["model_version"],
                            row.get("daily_load"),
                            row.get("fitness"),
                            row.get("fatigue"),
                            row.get("form"),
                            Jsonb(row),
                        ),
                    )
            if report:
                conn.execute(
                    "INSERT INTO athlete.reports(id,revision_id,metadata) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (report["id"], revision, Jsonb(report)),
                )
            conn.execute("UPDATE athlete.state SET active_revision=%s WHERE singleton", (revision,))
        FILES_CACHE.invalidate()
        return revision

    def _project(self, conn, revision, values):
        from psycopg.types.json import Jsonb

        get = lambda name, default: values.get("data/" + name + ".json", default)
        conn.execute(
            "INSERT INTO athlete.profiles VALUES(%s,%s,%s,%s,%s)",
            (
                revision,
                ATHLETE_ID,
                Jsonb(get("athlete_profile", {})),
                Jsonb(get("athlete_preferences", {})),
                Jsonb(get("season_goals", {})),
            ),
        )
        garmin, activities = {}, []
        for index, row in enumerate(get("training_history", [])):
            key = identity(row, ordinal=index)
            conn.execute(
                "INSERT INTO athlete.activities VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    revision,
                    key,
                    day(row.get("date")),
                    row.get("date_time"),
                    row.get("type"),
                    row.get("name"),
                    number(row.get("distance_km")),
                    duration(row),
                    number(row.get("avg_hr")),
                    number(row.get("max_hr")),
                    number(row.get("watch_elevation_gain_m")),
                    number(row.get("official_elevation_gain_m")),
                    Jsonb(row),
                ),
            )
            activities.append((key, row))
            if row.get("garmin_activity_id") is not None:
                external = str(row["garmin_activity_id"])
                if external in garmin:
                    raise RuntimeError("Duplicate Garmin activity ID requires review")
                garmin[external] = key
                conn.execute(
                    "INSERT INTO athlete.activity_sources VALUES(%s,%s,%s,%s,%s)",
                    (revision, key, "garmin", external, Jsonb(row)),
                )
        signature = lambda row: canonical([row.get(k) for k in ("date", "type", "name", "distance_km", "elapsed_time")])
        for index, row in enumerate(get("race_history", [])):
            candidates = [key for key, activity in activities if signature(activity) == signature(row)]
            linked = garmin.get(str(row.get("garmin_activity_id"))) or (candidates[0] if len(candidates) == 1 else None)
            conn.execute("INSERT INTO athlete.races VALUES(%s,%s,%s,%s)", (revision, index, linked, Jsonb(row)))
        hevy_rows = get("hevy_workouts", [])
        hevy = {str(x["hevy_workout_id"]): x for x in hevy_rows}
        if len(hevy) != len(hevy_rows):
            raise RuntimeError("Duplicate Hevy workout ID requires review")
        linked_hevy = {}
        for index, row in enumerate(get("strength_training_consolidated", [])):
            hid, gid = row.get("hevy_workout_id"), row.get("garmin_activity_id")
            sid = uuid.uuid5(ATHLETE_ID, "strength:" + str(hid or gid or index))
            aid = garmin.get(str(gid))
            if hid is not None:
                linked_hevy[str(hid)] = aid
            conn.execute(
                "INSERT INTO athlete.strength_sessions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    revision,
                    sid,
                    aid,
                    day(row.get("date")),
                    row.get("garmin_match_status"),
                    row.get("hevy_title"),
                    row.get("hevy_total_sets"),
                    row.get("hevy_working_sets"),
                    row.get("hevy_total_reps"),
                    number(row.get("hevy_total_volume_kg")),
                    Jsonb(row),
                ),
            )
            for ei, exercise in enumerate(hevy.get(str(hid), {}).get("exercises", [])):
                conn.execute(
                    "INSERT INTO athlete.exercises VALUES(%s,%s,%s,%s,%s)",
                    (revision, sid, ei, exercise.get("name"), Jsonb(exercise)),
                )
                for si, item in enumerate(exercise.get("sets", [])):
                    conn.execute(
                        "INSERT INTO athlete.exercise_sets VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            revision,
                            sid,
                            ei,
                            si,
                            item.get("set_type"),
                            number(item.get("weight_kg")),
                            item.get("reps"),
                            number(item.get("rpe")),
                            Jsonb(item),
                        ),
                    )
        for external, row in hevy.items():
            conn.execute(
                "INSERT INTO athlete.activity_sources VALUES(%s,%s,%s,%s,%s)",
                (revision, linked_hevy.get(external), "hevy", external, Jsonb(row)),
            )
        body = get("body_metrics", {})
        measurements = list(body.get("history") or [])
        if body.get("current"):
            measurements.append({"date": body.get("reference_date"), "reference": "current", **body["current"]})
        for index, row in enumerate(measurements):
            conn.execute(
                "INSERT INTO athlete.body_measurements VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    revision,
                    index,
                    day(row.get("date")),
                    number(row.get("weight_kg")),
                    number(row.get("waist_cm")),
                    number(row.get("body_fat_pct")),
                    number(row.get("lean_mass_kg")),
                    Jsonb(row),
                ),
            )
        for index, row in enumerate(get("medical_history", {}).get("records", [])):
            conn.execute(
                "INSERT INTO athlete.medical_records VALUES(%s,%s,%s,%s,%s,%s)",
                (revision, index, day(row.get("date")), row.get("type"), row.get("label"), Jsonb(row)),
            )

            def leaves(value, prefix=""):
                if isinstance(value, dict):
                    for k, v in value.items():
                        yield from leaves(v, prefix + "/" + k)
                else:
                    yield prefix, value

            for code, result in leaves(row):
                conn.execute(
                    "INSERT INTO athlete.medical_observations VALUES(%s,%s,%s,%s)",
                    (revision, index, code, Jsonb(result)),
                )
        for path, payload in values.items():
            if path.startswith("data/") and "sleep" in path and isinstance(payload, (dict, list)):
                rows = (
                    payload if isinstance(payload, list) else payload.get("daily_records", payload.get("records", []))
                )
                if isinstance(rows, list):
                    for index, row in enumerate(rows):
                        if isinstance(row, dict):
                            conn.execute(
                                "INSERT INTO athlete.sleep_records VALUES(%s,%s,%s,%s,%s)",
                                (
                                    revision,
                                    path,
                                    index,
                                    str(row.get("date") or row.get("calendar_date") or ""),
                                    Jsonb(row),
                                ),
                            )

    def counts(self, revision=None):
        from psycopg import sql

        revision = revision or self.active()
        tables = (
            "datasets",
            "activities",
            "races",
            "strength_sessions",
            "exercises",
            "exercise_sets",
            "body_measurements",
            "medical_records",
            "daily_metrics",
            "documents",
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
    if postgres_enabled(root):
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
    if files is None and postgres_enabled(root):
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


class OperationalConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, values=()):
        if query == "BEGIN IMMEDIATE":
            return self.conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID + 1,))
        if query.startswith("INSERT OR IGNORE"):
            query = query.replace("INSERT OR IGNORE", "INSERT", 1) + " ON CONFLICT DO NOTHING"
        query = (
            query.replace("?", "%s")
            .replace("rowid DESC", "id DESC")
            .replace("expires REAL", "expires double precision")
        )
        return self.conn.execute(query, values)


@contextmanager
def operational_db(runtime, name, root=ROOT):
    if postgres_enabled(root):
        with connect(row_factory=row_factory) as conn:
            conn.execute("SET search_path TO operations,public")
            yield OperationalConnection(conn)
    else:
        conn = sqlite3.connect(Path(runtime) / f"{name}.sqlite", timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def import_operations(runtime):
    from psycopg import sql

    with connect() as conn:
        for file, table in (("jobs", "jobs"), ("jobs", "settings"), ("sessions", "sessions")):
            path = runtime / f"{file}.sqlite"
            if not path.exists():
                continue
            local = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                for row in local.execute(f"SELECT * FROM {table}"):
                    query = sql.SQL("INSERT INTO operations.{} VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(table), sql.SQL(",").join(sql.Placeholder() for _ in row)
                    )
                    conn.execute(query, row)
            finally:
                local.close()


def document_manifest(root):
    from dashboard.backup import file_hash

    return {
        p.relative_to(root).as_posix(): {"sha256": file_hash(p), "bytes": p.stat().st_size}
        for p in sorted((root / "activities").rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
