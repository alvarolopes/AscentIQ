from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from dashboard.jobs import JobManager
from dashboard.snapshot import ROOT, build_snapshot, medical_documents
from dashboard.repository import connect, operational_db, postgres_enabled

RUNTIME = Path(os.environ.get("DASHBOARD_RUNTIME", str(ROOT / "runtime" / "dashboard")))
COOKIE = "ascentiq_session"


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


class JobRequest(BaseModel):
    mode: str


def create_app(runtime: Path = RUNTIME, root: Path = ROOT) -> FastAPI:
    runtime.mkdir(parents=True, exist_ok=True)
    auth_path = runtime / "auth.json"
    if not auth_path.exists():
        password = os.environ.get("DASHBOARD_PASSWORD") or secrets.token_urlsafe(18)
        salt = secrets.token_hex(16)
        auth = {"username": os.environ.get("DASHBOARD_USERNAME", "athlete"), "salt": salt,
                "hash": hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex()}
        auth_path.write_text(json.dumps(auth), encoding="utf-8")
        if not os.environ.get("DASHBOARD_PASSWORD"):
            access = runtime / "access.txt"
            access.write_text(f"AscentIQ - acesso privado local\nUsuário: {auth['username']}\nSenha: {password}\nURL: http://localhost:8787\n", encoding="utf-8")
            if os.name != "nt":
                access.chmod(0o600)
        if os.name != "nt":
            auth_path.chmod(0o600)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    session_db = runtime / "sessions.sqlite"

    @contextmanager
    def sessions():
        with operational_db(runtime, "sessions", root) as conn:
            yield conn

    with sessions() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires REAL)")
    manager = JobManager(runtime, root)
    attempts: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        yield
        manager.close()

    app = FastAPI(title="AscentIQ Private Dashboard", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.jobs = manager

    @app.middleware("http")
    async def protect(request: Request, call_next):
        path = request.url.path
        if request.method == "POST":
            origin = request.headers.get("origin")
            if request.headers.get("x-ascentiq-request") != "1" or (origin and urlsplit(origin).netloc != request.headers.get("host")):
                return Response(status_code=403)
        if path not in {"/api/health", "/api/auth/login"}:
            token = request.cookies.get(COOKIE, "")
            with sessions() as conn:
                row = conn.execute("SELECT expires FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not token or not row or row[0] <= time.time():
                return Response(status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        if postgres_enabled(root):
            with connect() as conn:
                conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(payload: Login, request: Request, response: Response):
        peer = request.client.host if request.client else "unknown"
        attempts[peer] = [stamp for stamp in attempts.get(peer, []) if stamp > time.time() - 60]
        if len(attempts[peer]) >= 8:
            raise HTTPException(429, "Muitas tentativas. Aguarde um minuto.")
        attempts[peer].append(time.time())
        digest = hashlib.pbkdf2_hmac("sha256", payload.password.encode(), bytes.fromhex(auth["salt"]), 310000).hex()
        if not hmac.compare_digest(payload.username, auth["username"]) or not hmac.compare_digest(digest, auth["hash"]):
            raise HTTPException(401, "Usuário ou senha incorretos.")
        token = secrets.token_urlsafe(32)
        with sessions() as conn:
            conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            conn.execute("INSERT INTO sessions VALUES (?, ?)", (hashlib.sha256(token.encode()).hexdigest(), time.time() + 86400 * 7))
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=os.environ.get("DASHBOARD_SECURE_COOKIES", "false") == "true", max_age=86400 * 7, path="/")
        return {"username": auth["username"]}

    @app.get("/api/auth/session")
    def session():
        return {"username": auth["username"]}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with sessions() as conn:
            conn.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(),))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    def latest_path() -> Path | None:
        path = runtime / "latest.json"
        if not path.exists():
            return None
        key = json.loads(path.read_text())["id"]
        return runtime / "reports" / key

    @app.get("/api/dashboard")
    def dashboard():
        if postgres_enabled(root):
            return build_snapshot(root)
        path = latest_path()
        if path:
            return json.loads((path / "snapshot.json").read_text(encoding="utf-8"))
        snapshot = build_snapshot(root)
        snapshot["report_pending"] = True
        return snapshot

    @app.get("/api/jobs")
    def jobs():
        return {"jobs": manager.list(), "schedule": "Segunda-feira, 07:00 (America/Sao_Paulo)",
                "schedule_enabled": os.environ.get("DASHBOARD_SCHEDULE_ENABLED", "true").lower() == "true"}

    @app.post("/api/jobs", status_code=202)
    def enqueue(payload: JobRequest):
        try:
            return {"id": manager.enqueue(payload.mode)}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/api/reports")
    def reports():
        if postgres_enabled(root):
            with connect() as conn:
                items = [row[0] for row in conn.execute("SELECT metadata FROM athlete.reports ORDER BY created_at DESC,id DESC")]
            return {"reports": [item for item in items if item.get("pdf_scope") == "training"]}
        paths = sorted((runtime / "reports").glob("*/meta.json"), reverse=True)
        items = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        return {"reports": [item for item in items if item.get("pdf_scope") == "training"]}

    @app.get("/api/reports/{report_id}/pdf")
    def report_pdf(report_id: str):
        if not all(c.isalnum() or c == "-" for c in report_id):
            raise HTTPException(404)
        if postgres_enabled(root):
            with connect() as conn:
                if not conn.execute("SELECT 1 FROM athlete.reports WHERE id=%s",(report_id,)).fetchone():
                    raise HTTPException(404)
        path = runtime / "reports" / report_id / "report.pdf"
        meta = path.parent / "meta.json"
        if not path.is_file() or not meta.is_file() or json.loads(meta.read_text(encoding="utf-8")).get("pdf_scope") != "training":
            raise HTTPException(404)
        return FileResponse(path, media_type="application/pdf", filename=f"AscentIQ-{report_id}.pdf")

    @app.get("/api/reports/{report_id}/html")
    def report_html(report_id: str):
        if not all(c.isalnum() or c == "-" for c in report_id):
            raise HTTPException(404)
        if postgres_enabled(root):
            with connect() as conn:
                if not conn.execute("SELECT 1 FROM athlete.reports WHERE id=%s",(report_id,)).fetchone():
                    raise HTTPException(404)
        path = runtime / "reports" / report_id / "dashboard.html"
        if not path.is_file():
            raise HTTPException(404)
        response = FileResponse(path, media_type="text/html")
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; frame-ancestors 'self'"
        return response

    @app.get("/api/reports/{report_id}/chart")
    def report_chart(report_id: str):
        if not all(c.isalnum() or c == "-" for c in report_id):
            raise HTTPException(404)
        folder = runtime / "reports" / report_id
        path = folder / "performance-dark.svg"
        if not path.is_file():
            path = folder / "performance.svg"
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/api/medical/documents/{document_id}")
    def document(document_id: str):
        path = medical_documents(root).get(document_id)
        if not path:
            raise HTTPException(404)
        return FileResponse(path, filename=path.name)

    return app
