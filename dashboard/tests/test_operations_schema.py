"""Operational state lives only in migrated PostgreSQL tables (jsonb payloads)."""

import hashlib
import json
import unittest
import uuid
from pathlib import Path

import dashboard.repository as repository
from dashboard.tests import pg


class OperationsSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.fresh_database(cls)

    def test_migrations_create_every_operational_table(self):
        with repository.connect() as conn:
            columns = {
                (row[0], row[1]): row[2]
                for row in conn.execute(
                    "SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='operations'"
                )
            }
        expected = {
            "personal_health_state": "payload",
            "personal_health_revisions": "payload",
            "personal_imports_state": "payload",
            "food_diary_state": "payload",
            "personal_artifacts": "payload",
            "jobs": "warnings",
        }
        for table, column in expected.items():
            self.assertEqual(columns.get((table, column)), "jsonb", f"{table}.{column} deve ser jsonb")
        tables = {table for table, _ in columns}
        self.assertEqual(
            tables,
            {
                "jobs",
                "settings",
                "sessions",
                "personal_health_state",
                "personal_health_revisions",
                "personal_imports_state",
                "food_diary_state",
                "personal_artifacts",
            },
        )
        with repository.connect() as conn:
            athlete_tables = {
                row[0]
                for row in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='athlete'")
            }
        self.assertEqual(
            athlete_tables,
            {"schema_migrations", "revisions", "state", "dataset_blobs", "datasets", "documents", "reports"},
        )

    def test_no_sqlite_or_create_table_in_runtime_code(self):
        sources = Path(repository.__file__).parent
        for path in sorted(sources.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sqlite" + "3", text, path.name)
            self.assertNotIn("CREATE " + "TABLE", text, path.name)

    def test_migration_005_converts_existing_text_payloads(self):
        name = "ascentiq_test_" + uuid.uuid4().hex[:8]
        with pg._admin() as conn:
            conn.execute(f'CREATE DATABASE "{name}"')

        context = repository.use_database(name)

        def cleanup():
            context.__exit__(None, None, None)
            with pg._admin() as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

        self.addCleanup(cleanup)
        context.__enter__()
        migrations = Path(repository.__file__).parent / "migrations"
        try:
            with repository.connect() as conn:
                conn.execute("CREATE SCHEMA IF NOT EXISTS athlete")
                conn.execute(
                    "CREATE "
                    + "TABLE IF NOT EXISTS athlete.schema_migrations(version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())"
                )
                for path in sorted(migrations.glob("00[1-4]_*.sql")):
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO athlete.schema_migrations(version,checksum) VALUES(%s,%s)",
                        (path.name, hashlib.sha256(path.read_bytes()).hexdigest()),
                    )
                payload = json.dumps({"entries": [], "revision": 3})
                conn.execute("INSERT INTO operations.food_diary_state VALUES('2026-01-01',%s)", (payload,))
                conn.execute(
                    "INSERT INTO operations.jobs VALUES('j1','generate','completed','2026-01-01','2026-01-01','ok','',NULL)"
                )
            repository.migrate()
            with repository.connect() as conn:
                row = conn.execute("SELECT payload FROM operations.food_diary_state").fetchone()
                self.assertEqual(row[0], {"entries": [], "revision": 3})
                self.assertIsInstance(row[0], dict)
                warnings = conn.execute("SELECT warnings FROM operations.jobs WHERE id='j1'").fetchone()
                self.assertEqual(warnings[0], [])
        finally:
            context.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
