"""The versioned OpenAPI contract must match the generated snapshot."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OpenApiContractTests(unittest.TestCase):
    def test_openapi_snapshot_is_current(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATABASE_BACKEND": "json"}):
            from dashboard.server import create_app
            spec = create_app(Path(folder)).openapi()
        target = Path(__file__).resolve().parents[1] / "openapi.json"
        self.assertTrue(target.is_file(), "dashboard/openapi.json missing; run python -m dashboard.openapi_export")
        self.assertEqual(target.read_text(encoding="utf-8"),
                         json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                         "dashboard/openapi.json is stale; run python -m dashboard.openapi_export")


if __name__ == '__main__':
    unittest.main()
