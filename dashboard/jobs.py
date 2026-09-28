from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from dashboard.pipeline import publish_report, rebuild, sync_sources
from dashboard.snapshot import ROOT, TZ, build_snapshot


@contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def schedule_slot(current: datetime) -> datetime:
    monday = current - timedelta(days=current.weekday())
    slot = monday.replace(hour=7, minute=0, second=0, microsecond=0)
    return slot if current >= slot else slot - timedelta(days=7)


class JobManager:
    def __init__(self, runtime: Path, root: Path = ROOT):
        self.runtime, self.root = runtime, root
        runtime.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.thread = None
        with self.db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, mode TEXT, status TEXT, created_at TEXT, finished_at TEXT, message TEXT, warnings TEXT, schedule_key TEXT UNIQUE)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("UPDATE jobs SET status='failed', message='Processo interrompido; execute novamente.' WHERE status='running'")
            slot = schedule_slot(datetime.now(TZ)).isoformat()
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('scheduled_slot', ?)", (slot,))

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.runtime / "jobs.sqlite", timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def list(self) -> list[dict]:
        with self.db() as conn:
            return [dict(x) for x in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT 30")]

    def enqueue(self, mode: str, schedule_key: str | None = None) -> str:
        if mode not in {"generate", "sync"}:
            raise ValueError("Modo inválido")
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute("SELECT id FROM jobs WHERE status IN ('queued','running')").fetchone()
            if active:
                raise RuntimeError("Uma atualização já está em andamento.")
            job_id = datetime.now(TZ).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            conn.execute("INSERT INTO jobs VALUES (?, ?, 'queued', ?, NULL, 'Aguardando execução', '[]', ?)", (job_id, mode, now(), schedule_key))
            return job_id

    def update(self, job_id: str, status: str, message: str, warnings: list | None = None):
        with self.db() as conn:
            conn.execute("UPDATE jobs SET status=?, message=?, warnings=?, finished_at=? WHERE id=?",
                         (status, message, json.dumps(warnings or [], ensure_ascii=False), now() if status in {"completed", "partial", "failed"} else None, job_id))

    def process(self, job: dict):
        try:
            with process_lock(self.runtime / "update.lock"):
                progress = lambda message: self.update(job["id"], "running", message)
                progress("Preparando dados")
                warnings = sync_sources(self.root, progress) if job["mode"] == "sync" else []
                rebuild(self.root, progress)
                snapshot = build_snapshot(self.root)
                snapshot["sync_warnings"] = warnings
                progress("Gerando e validando PDF Typst")
                publish_report(snapshot, job["id"], self.runtime, self.root)
                self.update(job["id"], "partial" if warnings else "completed", "Relatório publicado" if not warnings else "Relatório publicado com fontes parciais", warnings)
        except Exception as error:
            message = str(error) if isinstance(error, RuntimeError) else "Falha ao gerar o relatório; a versão anterior foi preservada."
            self.update(job["id"], "failed", message)

    def tick_schedule(self, current: datetime):
        if os.environ.get("DASHBOARD_SCHEDULE_ENABLED", "true").lower() != "true":
            return
        slot = schedule_slot(current).isoformat()
        with self.db() as conn:
            previous = conn.execute("SELECT value FROM settings WHERE key='scheduled_slot'").fetchone()[0]
        if slot > previous:
            try:
                self.enqueue("sync", schedule_key=slot)
            except (RuntimeError, sqlite3.IntegrityError):
                return
            with self.db() as conn:
                conn.execute("UPDATE settings SET value=? WHERE key='scheduled_slot'", (slot,))

    def loop(self):
        while not self.stop.is_set():
            self.tick_schedule(datetime.now(TZ))
            with self.db() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                self.process(dict(row))
            self.stop.wait(2)

    def start(self):
        if not (self.runtime / "latest.json").exists() and not any(x["status"] in {"queued", "running"} for x in self.list()):
            self.enqueue("generate")
        self.thread = threading.Thread(target=self.loop, name="athlete-jobs", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
