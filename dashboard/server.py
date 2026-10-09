from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from dashboard.daily_analysis import DailyReports, configuration, prepare
from dashboard.jobs import JobManager
from dashboard.nutrition import FoodDiary, estimate, prompt, validate
from dashboard.repository import connect, migrate, operational_db
from dashboard.snapshot import ROOT, build_snapshot, medical_documents

RUNTIME = Path(os.environ.get("DASHBOARD_RUNTIME", str(ROOT / "runtime" / "dashboard")))
COOKIE = "ascentiq_session"


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


class JobRequest(BaseModel):
    mode: str


class AnalysisRequest(BaseModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    text: str | None = Field(default=None, min_length=20, max_length=30000)


class FoodRequest(BaseModel):
    text: str = Field(min_length=3, max_length=10000)
    meal: str = Field(default='Refeição', min_length=1, max_length=80)
    analysis: dict | None = None
    id: uuid.UUID | None = None
    revision: int | None = Field(default=None, ge=0)
    image: str | None = Field(default=None, max_length=9000000)
    estimate_on_save: bool = False
    save_token: uuid.UUID | None = None


class FoodRemove(BaseModel):
    id: uuid.UUID
    revision: int | None = Field(default=None, ge=0)


class FoodCoverage(BaseModel):
    completeness: str
    fasting_declared: bool = False
    revision: int | None = Field(default=None, ge=0)


class FoodRestore(BaseModel):
    restore_revision: int = Field(ge=0)
    revision: int | None = Field(default=None, ge=0)


VALIDATION_MESSAGES = (
    ("missing", "campo obrigatório"),
    ("bool_type", "informe verdadeiro ou falso"),
    ("bool_parsing", "informe verdadeiro ou falso"),
    ("is_instance_of", "valor inválido"),
    ("string_type", "informe um texto"),
    ("int_type", "informe um número inteiro"),
    ("int_parsing", "informe um número inteiro"),
    ("float_", "informe um número"),
    ("date_", "informe uma data válida no formato AAAA-MM-DD"),
    ("list_type", "informe uma lista"),
    ("dict_type", "informe um objeto"),
    ("literal_error", "valor não permitido"),
    ("greater_than_equal", "valor fora do limite permitido"),
    ("less_than_equal", "valor fora do limite permitido"),
    ("string_too_long", "valor fora do limite permitido"),
    ("string_too_short", "valor fora do limite permitido"),
)


def validation_detail(error):
    kind, context = error.get("type", ""), error.get("ctx") or {}
    if kind == "value_error" and context.get("error") is not None:
        message = str(context["error"])
    else:
        message = next(
            (text for prefix, text in VALIDATION_MESSAGES if kind == prefix or kind.startswith(prefix)),
            "valor inválido",
        )
    message = message if message.endswith(".") else message + "."
    field = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
    return f"{field}: {message}" if field else message


def create_app(runtime: Path = RUNTIME, root: Path = ROOT) -> FastAPI:
    runtime.mkdir(parents=True, exist_ok=True)
    if os.environ.get("ASCENTIQ_AUTO_MIGRATE", "false").lower() == "true":
        migrate()
    auth_path = runtime / "auth.json"
    if not auth_path.exists():
        password = os.environ.get("DASHBOARD_PASSWORD") or secrets.token_urlsafe(18)
        salt = secrets.token_hex(16)
        auth = {
            "username": os.environ.get("DASHBOARD_USERNAME", "alvaro"),
            "salt": salt,
            "hash": hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex(),
        }
        auth_path.write_text(json.dumps(auth), encoding="utf-8")
        if not os.environ.get("DASHBOARD_PASSWORD"):
            access = runtime / "access.txt"
            access.write_text(
                f"AscentIQ - acesso privado local\nUsuário: {auth['username']}\nSenha: {password}\nURL: http://localhost:8787\n",
                encoding="utf-8",
            )
            if os.name != "nt":
                access.chmod(0o600)
        if os.name != "nt":
            auth_path.chmod(0o600)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))

    @contextmanager
    def sessions():
        with operational_db() as conn:
            yield conn

    manager = JobManager(runtime, root)
    daily_reports = DailyReports(runtime)
    food_diary = FoodDiary(runtime, root)
    attempts: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        app.state.nutrition_targets.start()
        yield
        app.state.nutrition_targets.close()
        manager.close()

    openapi_route = os.environ.get("ASCENTIQ_OPENAPI", "false").lower() == "true"
    app = FastAPI(
        title="AscentIQ Private Dashboard",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if openapi_route else None,
    )
    app.state.jobs = manager
    public = {"/api/health", "/api/auth/login"} | ({"/api/openapi.json"} if openapi_route else set())

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        errors = error.errors()
        return JSONResponse({"detail": validation_detail(errors[0]) if errors else "valor inválido."}, status_code=400)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        path = request.url.path
        if request.method == "POST":
            origin = request.headers.get("origin")
            if request.headers.get("x-ascentiq-request") != "1" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return Response(status_code=403)
        if path not in public:
            token = request.cookies.get(COOKIE, "")
            with sessions() as conn:
                row = conn.execute(
                    "SELECT expires FROM sessions WHERE digest=%s", (hashlib.sha256(token.encode()).hexdigest(),)
                ).fetchone()
            if not token or not row or row[0] <= time.time():
                return Response(status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
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
            conn.execute("DELETE FROM sessions WHERE expires < %s", (time.time(),))
            conn.execute(
                "INSERT INTO sessions VALUES (%s, %s)",
                (hashlib.sha256(token.encode()).hexdigest(), time.time() + 86400 * 7),
            )
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=os.environ.get("DASHBOARD_SECURE_COOKIES", "false") == "true",
            max_age=86400 * 7,
            path="/",
        )
        return {"username": auth["username"]}

    @app.get("/api/auth/session")
    def session():
        return {"username": auth["username"]}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with sessions() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE digest=%s",
                (hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(),),
            )
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    def latest_path() -> Path | None:
        path = runtime / "latest.json"
        if not path.exists():
            return None
        key = json.loads(path.read_text())["id"]
        return runtime / "reports" / key

    def live_snapshot():
        return app.state.personal_snapshot() if hasattr(app.state, 'personal_snapshot') else build_snapshot(root)

    @app.get("/api/dashboard")
    def dashboard():
        snapshot = live_snapshot()
        snapshot["report_pending"] = latest_path() is None
        return snapshot

    @app.get("/api/daily-analysis/{day}")
    def daily_analysis(day: date):
        prepared = prepare(live_snapshot(), day)
        saved = daily_reports.read(day)
        return {
            **prepared,
            **configuration(),
            "report": saved,
            "stale": bool(saved and saved["fingerprint"] != prepared["fingerprint"]),
        }

    @app.post("/api/daily-analysis/{day}")
    def generate_daily_analysis(day: date, payload: AnalysisRequest):
        prepared = prepare(live_snapshot(), day)
        if payload.fingerprint != prepared["fingerprint"]:
            raise HTTPException(409, "Os treinos mudaram. Consulte o dia novamente antes de gerar ou importar.")
        if payload.text is not None and len(payload.text.strip()) < 20:
            raise HTTPException(400, "Cole o relatório completo antes de salvar.")
        try:
            return daily_reports.save(prepared, payload.text.strip() if payload.text is not None else None)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @app.get('/api/food/{day}')
    def food(day: date):
        return {**food_diary.read(day), **configuration(), 'targets': app.state.nutrition_targets.view(day)}

    @app.get('/api/ai/configuration')
    def ai_configuration():
        return configuration()

    @app.post('/api/food/{day}/analyze')
    def analyze_food(day: date, payload: FoodRequest):
        if not payload.text.strip():
            raise HTTPException(400, 'Descreva sua refeição.')
        try:
            if payload.analysis is not None:
                return {**validate(payload.analysis), 'source': 'imported', 'model': 'Resposta importada'}
            return estimate(payload.text, payload.image)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @app.post('/api/food/{day}/prompt')
    def food_prompt(day: date, payload: FoodRequest):
        return {'prompt': prompt(payload.text)}

    @app.post('/api/food/{day}/save')
    def save_food(day: date, payload: FoodRequest):
        try:
            analysis = (
                validate(payload.analysis, allow_unknown=True)
                if payload.analysis is not None and not payload.estimate_on_save
                else None
            )
            current = food_diary.read(day)
            identifier = str(payload.id or uuid.uuid4())
            previous = next((x for x in current['entries'] if x['id'] == identifier), None)
            image_id = None
            if payload.image:
                image_id = app.state.food_image(payload.image)
            elif previous:
                image_id = previous.get('image_id') if previous else None
            token = str(payload.save_token) if payload.save_token else None
            if (
                payload.estimate_on_save
                and token
                and previous
                and previous.get('save_token') == token
                and previous.get('text') == payload.text
                and previous.get('meal') == payload.meal
                and previous.get('image_id') == image_id
                and previous.get('source') == 'ai_estimated'
                and previous.get('analysis')
            ):
                return {**current, 'analysis_status': 'estimated'}
            entry = {
                'id': identifier,
                'meal': payload.meal,
                'text': payload.text,
                'analysis': analysis,
                'image_id': image_id,
                'created_at': datetime.now(UTC).isoformat(),
                'source': 'reviewed' if analysis else 'pending',
                **({'save_token': token} if payload.estimate_on_save else {}),
            }
            saved = food_diary.change(day, entry=entry, expected_revision=payload.revision)
            if not payload.estimate_on_save:
                return saved
            # Persist first: an unavailable model must never lose the meal.
            try:
                image = app.state.food_image_content(image_id) if image_id else None
                analysis = estimate(payload.text, image)
            except (ValueError, RuntimeError) as error:
                return {**saved, 'analysis_status': 'pending', 'analysis_error': str(error)}
            completed = food_diary.change(
                day,
                entry={**entry, 'analysis': analysis, 'source': 'ai_estimated'},
                expected_revision=saved['revision'],
            )
            return {**completed, 'analysis_status': 'estimated'}
        except ValueError as error:
            raise HTTPException(409 if 'mudou' in str(error) else 400, str(error)) from error

    @app.post('/api/food/{day}/remove')
    def remove_food(day: date, payload: FoodRemove):
        try:
            return food_diary.change(day, remove=str(payload.id), expected_revision=payload.revision)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.post('/api/food/{day}/coverage')
    def food_coverage(day: date, payload: FoodCoverage):
        try:
            return food_diary.change(
                day,
                completeness=payload.completeness,
                fasting_declared=payload.fasting_declared,
                expected_revision=payload.revision,
            )
        except ValueError as error:
            raise HTTPException(409 if 'mudou' in str(error) else 400, str(error)) from error

    @app.post('/api/food/{day}/restore')
    def restore_food(day: date, payload: FoodRestore):
        try:
            return food_diary.change(day, restore_revision=payload.restore_revision, expected_revision=payload.revision)
        except ValueError as error:
            raise HTTPException(409 if 'mudou' in str(error) else 400, str(error)) from error

    @app.get("/api/jobs")
    def jobs():
        return {
            "jobs": manager.list(),
            "schedule": "Relatório semanal: segunda, 07h. Garmin e sono: diariamente, 10h (America/Sao_Paulo); até 3 tentativas com intervalo de 1h.",
            "sleep_schedule_enabled": os.environ.get("DASHBOARD_SLEEP_SCHEDULE_ENABLED", "true").lower() == "true",
            "schedule_enabled": os.environ.get("DASHBOARD_SCHEDULE_ENABLED", "true").lower() == "true",
        }

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
        with connect() as conn:
            items = [
                row[0] for row in conn.execute("SELECT metadata FROM athlete.reports ORDER BY created_at DESC,id DESC")
            ]
        return {"reports": [item for item in items if item.get("pdf_scope") == "training"]}

    @app.get("/api/reports/{report_id}/pdf")
    def report_pdf(report_id: str):
        if not all(c.isalnum() or c == "-" for c in report_id):
            raise HTTPException(404)
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM athlete.reports WHERE id=%s", (report_id,)).fetchone():
                raise HTTPException(404)
        path = runtime / "reports" / report_id / "report.pdf"
        meta = path.parent / "meta.json"
        if (
            not path.is_file()
            or not meta.is_file()
            or json.loads(meta.read_text(encoding="utf-8")).get("pdf_scope") != "training"
        ):
            raise HTTPException(404)
        return FileResponse(path, media_type="application/pdf", filename=f"AscentIQ-{report_id}.pdf")

    @app.get("/api/reports/{report_id}/html")
    def report_html(report_id: str):
        if not all(c.isalnum() or c == "-" for c in report_id):
            raise HTTPException(404)
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM athlete.reports WHERE id=%s", (report_id,)).fetchone():
                raise HTTPException(404)
        path = runtime / "reports" / report_id / "dashboard.html"
        if not path.is_file():
            raise HTTPException(404)
        response = FileResponse(path, media_type="text/html")
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; frame-ancestors 'self'"
        )
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

    from dashboard.personal_api import install_personal_routes

    install_personal_routes(app, runtime, root, food_diary, manager)
    return app
