"""First-use PostgreSQL smoke, only before fixtures in a disposable empty DB."""

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.database_cli import initialize_empty
from dashboard.repository import ROOT, PostgresRepository
from dashboard.server import create_app


def main():
    if os.environ.get("DATABASE_TEST_ENABLED") != "1" or not os.environ.get("PGDATABASE", "").startswith(
        "ascentiq_test_"
    ):
        raise RuntimeError("First-use smoke requires a disposable test database")
    os.environ.update(
        DATABASE_BACKEND="postgres",
        DASHBOARD_USERNAME="tester",
        DASHBOARD_PASSWORD="synthetic-login-password",
        DASHBOARD_SCHEDULE_ENABLED="false",
        DASHBOARD_SLEEP_SCHEDULE_ENABLED="false",
        OPENAI_API_KEY="",
        GARMIN_EMAIL="",
        GARMIN_PASSWORD="",
        HEVY_API_KEY="",
    )
    result = initialize_empty()
    assert result["counts"]["datasets"] == 0
    assert initialize_empty()["revision"] == result["revision"]
    assert PostgresRepository().files()[1] == {}
    with tempfile.TemporaryDirectory() as folder:
        app = create_app(Path(folder), ROOT)
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/personal").status_code == 401
            login = client.post(
                "/api/auth/login",
                headers={"X-AscentIQ-Request": "1"},
                json={"username": "tester", "password": "synthetic-login-password"},
            )
            assert login.status_code == 200, login.text
            response = client.get("/api/personal")
            assert response.status_code == 200, response.text
            state = response.json()["state"]
            assert not state["goals"] and not state["measurements"] and not state["profile"]
            assert response.json()["summary"]["energy"]["deficit_kcal"] is None
            assert client.get("/api/dashboard").json()["activities"] == []
    print("Empty PostgreSQL installation: initialized, authenticated, no invented data")


if __name__ == "__main__":
    main()
