"""Immutable application settings, loaded once and installed explicitly.

`Settings.from_env` is the only place that reads `os.environ` for app
configuration. `install` registers the instance used by `current()`;
tests replace it atomically with `override`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    runtime: Path
    auto_migrate: bool
    openapi: bool
    revision_cache: bool
    operations_schema: str
    username: str
    initial_password: str | None
    secure_cookies: bool
    schedule_enabled: bool
    sleep_schedule_enabled: bool
    ai_provider: str
    ai_enabled: bool
    ollama_model: str
    ollama_base_url: str
    openai_model: str
    openai_api_key: str | None
    timezone: str
    garmin_mcp_command: str
    sync_start_date: date
    sync_max_activities: int
    sync_max_detail_activities: int
    typst_bin: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def get(key: str, default: str = "") -> str:
            return env.get(key, default)

        truthy = lambda value: str(value).lower() == "true"
        return cls(
            runtime=Path(get("DASHBOARD_RUNTIME", str(ROOT / "runtime" / "dashboard"))),
            auto_migrate=truthy(get("ASCENTIQ_AUTO_MIGRATE", "false")),
            openapi=truthy(get("ASCENTIQ_OPENAPI", "false")),
            revision_cache=get("ASCENTIQ_REVISION_CACHE") != "false",
            operations_schema=get("ASCENTIQ_OPERATIONS_SCHEMA", "operations"),
            username=get("DASHBOARD_USERNAME", "alvaro"),
            initial_password=get("DASHBOARD_PASSWORD") or None,
            secure_cookies=get("DASHBOARD_SECURE_COOKIES", "false") == "true",
            schedule_enabled=truthy(get("DASHBOARD_SCHEDULE_ENABLED", "true")),
            sleep_schedule_enabled=truthy(get("DASHBOARD_SLEEP_SCHEDULE_ENABLED", "true")),
            ai_provider=get("ASCENTIQ_AI_PROVIDER", "openai").strip().lower(),
            ai_enabled=get("ASCENTIQ_AI_ENABLED", "true") == "true",
            ollama_model=get("OLLAMA_MODEL", "qwen3.5:4b").strip() or "qwen3.5:4b",
            ollama_base_url=get("OLLAMA_BASE_URL", "http://ollama:11434"),
            openai_model=get("OPENAI_MODEL", "gpt-5"),
            openai_api_key=get("OPENAI_API_KEY") or None,
            timezone=get("TZ", "America/Sao_Paulo"),
            garmin_mcp_command=get("GARMIN_MCP_COMMAND", "mcp-garmin"),
            sync_start_date=date.fromisoformat(get("TRAINING_SYNC_START_DATE", "2024-01-01")),
            sync_max_activities=int(get("TRAINING_SYNC_MAX_ACTIVITIES", "5000")),
            sync_max_detail_activities=int(get("TRAINING_SYNC_MAX_DETAIL_ACTIVITIES", "300")),
            typst_bin=get("TYPST_BIN", "typst"),
        )


_current: Settings | None = None


def install(settings: Settings) -> None:
    global _current
    _current = settings


def current() -> Settings:
    global _current
    if _current is None:
        _current = Settings.from_env()
    return _current


@contextmanager
def override(**changes) -> Iterator[Settings]:
    previous = current()
    install(replace(previous, **changes))
    try:
        yield current()
    finally:
        install(previous)


def default_tz() -> ZoneInfo:
    return ZoneInfo(current().timezone)
