"""Disposable per-class PostgreSQL databases for the test suite.

Every class that touches operational state (sessions, jobs, health, food
diary, artifacts, imports) gets its own database cloned from a migrated
template, so tests stay isolated without translating SQL dialects.
"""

import contextlib
import os
import unittest
import uuid

import dashboard.repository as repository

TEMPLATE = "ascentiq_test_template"


def require():
    if not os.environ.get("PGDATABASE", "").startswith("ascentiq_test_"):
        raise unittest.SkipTest("Disposable PostgreSQL required: point PGDATABASE at an ascentiq_test_* database")


def _admin():
    return repository.connect(dbname="postgres", autocommit=True)


def ensure_template():
    require()
    with _admin() as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (TEMPLATE,)).fetchone():
            conn.execute(f'CREATE DATABASE "{TEMPLATE}"')
    previous = os.environ.get("PGDATABASE")
    os.environ["PGDATABASE"] = TEMPLATE
    try:
        repository.migrate()
    finally:
        if previous is not None:
            os.environ["PGDATABASE"] = previous


def reset_database():
    """Empty every data table of the current test database (schema kept)."""
    with repository.connect(autocommit=True) as conn:
        rows = conn.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema IN ('athlete', 'operations', 'imports')
              AND table_type = 'BASE TABLE'
              AND table_name != 'schema_migrations'
            """
        ).fetchall()
        tables = [f'"{schema}"."{table}"' for schema, table in rows]
        if tables:
            conn.execute("TRUNCATE " + ", ".join(tables) + " CASCADE")
        conn.execute("INSERT INTO athlete.state(singleton) VALUES(true) ON CONFLICT DO NOTHING")


@contextlib.contextmanager
def temp_database():
    """Point PGDATABASE at a new migrated database inside the block.

    For tests that need two isolated operational stores at once (for example a
    populated HealthStore next to an empty one) now that operational state no
    longer follows the runtime directory.
    """
    ensure_template()
    name = "ascentiq_test_" + uuid.uuid4().hex[:8]
    with _admin() as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{TEMPLATE}"')
    previous = os.environ.get("PGDATABASE")
    os.environ["PGDATABASE"] = name
    try:
        yield name
    finally:
        if previous is not None:
            os.environ["PGDATABASE"] = previous
        with _admin() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def fresh_database(case):
    ensure_template()
    name = "ascentiq_test_" + uuid.uuid4().hex[:8]
    with _admin() as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{TEMPLATE}"')
    previous = os.environ.get("PGDATABASE")
    os.environ["PGDATABASE"] = name

    def drop():
        try:
            with _admin() as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            if previous is not None:
                os.environ["PGDATABASE"] = previous

    case.addClassCleanup(drop)

    # Tests within a class used to get a fresh temp dir each; the shared class
    # database needs the same per-test isolation.
    original_set_up = case.setUp

    def set_up(self):
        reset_database()
        original_set_up(self)

    case.setUp = set_up
    return name
