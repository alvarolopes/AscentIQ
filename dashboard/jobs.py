from __future__ import annotations

import builtins
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from dashboard.repository import operational_db, operational_lock
from dashboard.settings import default_tz
from dashboard.snapshot import ROOT


@contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def now() -> str:
    return datetime.now(default_tz()).isoformat(timespec="seconds")


def schedule_slot(current: datetime) -> datetime:
    monday = current - timedelta(days=current.weekday())
    slot = monday.replace(hour=7, minute=0, second=0, microsecond=0)
    return slot if current >= slot else slot - timedelta(days=7)


def sleep_schedule_slot(current: datetime) -> datetime:
    slot = current.astimezone(default_tz()).replace(hour=10, minute=0, second=0, microsecond=0)
    return slot if current >= slot else slot - timedelta(days=1)


class JobManager:
    def __init__(
        self,
        settings,
        runtime: Path,
        root: Path = ROOT,
        *,
        preferences=lambda: {},
        providers=None,
        recover_interrupted: bool = True,
    ):
        self.settings = settings
        self.runtime, self.root = runtime, root
        self._preferences = preferences
        self.providers = providers
        runtime.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        with self.db() as conn:
            if recover_interrupted:
                conn.execute(
                    "UPDATE jobs SET status='failed', message='Processo interrompido; execute novamente.' WHERE status='running'"
                )
            slot = schedule_slot(datetime.now(default_tz())).isoformat()
            conn.execute("INSERT INTO settings VALUES ('scheduled_slot', %s) ON CONFLICT DO NOTHING", (slot,))

    @contextmanager
    def db(self):
        with operational_db() as conn:
            yield conn

    def list(self) -> list[dict]:
        with self.db() as conn:
            return [dict(x) for x in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT 30")]

    def enqueue(self, mode: str, schedule_key: str | None = None) -> str:
        if mode not in {"generate", "sync", "sync-garmin", "sync-hevy"}:
            raise ValueError("Modo inválido")
        with self.db() as conn:
            operational_lock(conn)
            active = conn.execute("SELECT id FROM jobs WHERE status IN ('queued','running')").fetchone()
            if active:
                raise RuntimeError("Uma atualização já está em andamento.")
            job_id = datetime.now(default_tz()).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            conn.execute(
                "INSERT INTO jobs VALUES (%s, %s, 'queued', %s, NULL, 'Aguardando execução', %s, %s)",
                (job_id, mode, now(), Jsonb([]), schedule_key),
            )
            return job_id

    def update(self, job_id: str, status: str, message: str, warnings: builtins.list | None = None):
        with self.db() as conn:
            conn.execute(
                "UPDATE jobs SET status=%s, message=%s, warnings=%s, finished_at=%s WHERE id=%s",
                (
                    status,
                    message,
                    Jsonb(warnings or []),
                    now() if status in {"completed", "partial", "failed"} else None,
                    job_id,
                ),
            )

    def process(self, job: dict):
        with self.db() as conn:
            claimed = conn.execute(
                "UPDATE jobs SET status='running' WHERE id=%s AND status='queued' RETURNING id", (job["id"],)
            ).fetchone()
        if not claimed:
            return
        try:
            with process_lock(self.runtime / "update.lock"):
                progress = lambda message: self.update(job["id"], "running", message)
                progress("Preparando dados")
                from dashboard.database_pipeline import run_database_pipeline

                warnings = run_database_pipeline(
                    job, self.root, self.runtime, progress, providers=self.providers, settings=self.settings
                )
                self.update(
                    job["id"],
                    "partial" if warnings else "completed",
                    "Relatorio publicado" if not warnings else "Relatorio publicado com fontes parciais",
                    warnings,
                )
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, RuntimeError)
                else "Falha ao gerar o relatório; a versão anterior foi preservada."
            )
            self.update(job["id"], "failed", message)

    def tick_schedule(self, current: datetime):
        if not self._preferences().get("weekly_sync", self.settings.schedule_enabled):
            return
        slot = schedule_slot(current).isoformat()
        with self.db() as conn:
            previous = conn.execute("SELECT value FROM settings WHERE key='scheduled_slot'").fetchone()[0]
        if slot > previous:
            try:
                self.enqueue("sync", schedule_key=slot)
            except RuntimeError, psycopg.IntegrityError:
                return
            with self.db() as conn:
                conn.execute("UPDATE settings SET value=%s WHERE key='scheduled_slot'", (slot,))

    def tick_sleep_schedule(self, current: datetime):
        if not self._preferences().get("daily_sync", self.settings.sleep_schedule_enabled):
            return
        prefix = 'daily-sleep:' + sleep_schedule_slot(current).date().isoformat() + ':'
        with self.db() as conn:
            attempts = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM jobs WHERE schedule_key LIKE %s ORDER BY created_at DESC", (prefix + '%',)
                )
            ]
        if any(job['status'] in ('completed', 'queued', 'running') for job in attempts) or len(attempts) >= 3:
            return
        if attempts:
            last = max(datetime.fromisoformat(job['finished_at'] or job['created_at']) for job in attempts)
            if current - last < timedelta(hours=1):
                return
        try:
            self.enqueue('sync-garmin', schedule_key=prefix + str(len(attempts) + 1))
        except RuntimeError, psycopg.IntegrityError:
            return

    def loop(self):
        while not self.stop.is_set():
            self.tick_schedule(datetime.now(default_tz()))
            self.tick_sleep_schedule(datetime.now(default_tz()))
            with self.db() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                self.process(dict(row))
            self.stop.wait(2)

    def start(self):
        if not (self.runtime / "latest.json").exists() and not any(
            x["status"] in {"queued", "running"} for x in self.list()
        ):
            self.enqueue("generate")
        self.thread = threading.Thread(target=self.loop, name="athlete-jobs", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
