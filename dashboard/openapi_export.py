"""Regenerate or verify the versioned OpenAPI contract at dashboard/openapi.json."""
import json
import os
import sys
import tempfile
from pathlib import Path


def main():
    os.environ.setdefault("DATABASE_BACKEND", "json")
    from dashboard.server import create_app
    target = Path(__file__).parent / "openapi.json"
    with tempfile.TemporaryDirectory() as folder:
        content = json.dumps(create_app(Path(folder)).openapi(), sort_keys=True,
                             indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            sys.exit("dashboard/openapi.json is stale; run python -m dashboard.openapi_export")
        print("dashboard/openapi.json is current")
    else:
        target.write_text(content, encoding="utf-8")
        print(f"dashboard/openapi.json regenerated ({len(content)} bytes)")


if __name__ == "__main__":
    main()
