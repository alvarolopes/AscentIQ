"""Browser QA harness: an empty installation with disposable synthetic data.

Run only in an isolated container with no production mounts or environment.
ASGI dispatch matches nginx: static UI public, all personal API authenticated.
"""
import os
import tempfile
from pathlib import Path

from starlette.staticfiles import StaticFiles

from dashboard.server import create_app

os.environ.update(DATABASE_BACKEND="json", DASHBOARD_USERNAME="tester",
                  DASHBOARD_PASSWORD="synthetic-login-password",
                  DASHBOARD_SCHEDULE_ENABLED="false", DASHBOARD_SLEEP_SCHEDULE_ENABLED="false",
                  OPENAI_API_KEY="", GARMIN_EMAIL="", GARMIN_PASSWORD="", HEVY_API_KEY="")
root = Path(tempfile.mkdtemp(prefix="ascentiq-browser-qa-"))
(root / "data").mkdir()
api = create_app(root / "runtime", root)
static = StaticFiles(directory=os.environ.get("PREVIEW_STATIC", "/preview"), html=True)


async def app(scope, receive, send):
    if scope["type"] == "http" and not scope["path"].startswith("/api/"):
        await static(scope, receive, send)
    else:
        await api(scope, receive, send)
