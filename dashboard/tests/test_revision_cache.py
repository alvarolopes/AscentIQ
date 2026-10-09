"""Revision-scoped in-memory caches, using synthetic data only."""
import unittest
import uuid
from datetime import date
from unittest.mock import patch

import dashboard.snapshot as snapshot_module
from dashboard.repository import FILES_CACHE, ROOT, SNAPSHOT_CACHE, PostgresRepository, RevisionCache, read_dataset
from dashboard.snapshot import build_snapshot


class RevisionCacheTests(unittest.TestCase):
    def setUp(self):
        FILES_CACHE.invalidate()
        SNAPSHOT_CACHE.invalidate()

    def tearDown(self):
        FILES_CACHE.invalidate()
        SNAPSHOT_CACHE.invalidate()

    def test_get_calls_loader_once_per_revision(self):
        cache = RevisionCache()
        revision = uuid.uuid4()
        calls = []
        def loader():
            calls.append(1)
            return {"path": b"raw"}
        first = cache.get(revision, loader)
        second = cache.get(revision, loader)
        self.assertEqual(len(calls), 1)
        self.assertIs(first, second)

    def test_new_revision_replaces_previous(self):
        cache = RevisionCache()
        first, second = uuid.uuid4(), uuid.uuid4()
        calls = []
        def loader():
            calls.append(1)
            return {}
        cache.get(first, loader)
        cache.get(second, loader)
        cache.get(first, loader)
        self.assertEqual(len(calls), 3)

    def test_invalidate_forces_reload(self):
        cache = RevisionCache()
        revision = uuid.uuid4()
        calls = []
        def loader():
            calls.append(1)
            return {}
        cache.get(revision, loader)
        cache.invalidate()
        cache.get(revision, loader)
        self.assertEqual(len(calls), 2)

    def test_parsed_returns_cached_object_and_read_dataset_copies(self):
        revision = uuid.uuid4()
        raw = b'{"a": 1}'
        with patch("dashboard.repository.postgres_enabled", return_value=True), \
             patch.object(PostgresRepository, "files", return_value=(revision, {"data/x.json": raw})):
            parsed = FILES_CACHE.parsed(revision, "data/x.json", raw)
            self.assertIs(parsed, FILES_CACHE.parsed(revision, "data/x.json", raw))
            first = read_dataset(ROOT, "data/x.json")
            first["a"] = 999
            second = read_dataset(ROOT, "data/x.json")
            self.assertEqual(second, {"a": 1})
            self.assertIsNot(first, second)

    def test_build_snapshot_uses_cache_per_revision_and_day(self):
        revision = uuid.uuid4()
        calls = []

        def counting(root, today=None):
            calls.append(today)
            return {"as_of": today.isoformat(), "nested": {"items": []}}

        with patch("dashboard.repository.postgres_enabled", return_value=True), \
             patch("dashboard.snapshot.postgres_enabled", return_value=True), \
             patch.object(PostgresRepository, "files", return_value=(revision, {})), \
             patch("dashboard.snapshot.revision_metadata", return_value=None), \
             patch.object(snapshot_module, "_build_snapshot", side_effect=counting):
            first = build_snapshot(ROOT, date(2026, 1, 10))
            build_snapshot(ROOT, date(2026, 1, 10))
            self.assertEqual(len(calls), 1)
            first["nested"]["items"].append("mutated")
            self.assertEqual(build_snapshot(ROOT, date(2026, 1, 10))["nested"]["items"], [])
            build_snapshot(ROOT, date(2026, 1, 11))
            self.assertEqual(len(calls), 2)
            SNAPSHOT_CACHE.invalidate()
            build_snapshot(ROOT, date(2026, 1, 11))
            self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
