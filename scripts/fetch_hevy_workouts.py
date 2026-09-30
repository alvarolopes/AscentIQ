from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from env_utils import load_dotenv
except ModuleNotFoundError:  # Support importing this file as scripts.fetch_hevy_workouts in tests.
    from scripts.env_utils import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
EXPORT_DIR = ROOT / "data" / "hevy_api_exports"
DEFAULT_OUTPUT = EXPORT_DIR / "hevy_workouts_latest.json"


class HevyApiError(RuntimeError):
    pass


class HevyClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(
            url,
            headers={
                "accept": "application/json",
                "api-key": self.api_key,
                "user-agent": "AscentIQ-Athlete-Agent/1.0",
            },
            method="GET",
        )

        for attempt in range(1, 4):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code == 429 or 500 <= exc.code < 600:
                    if attempt < 3:
                        retry_after = exc.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else attempt * 2.0
                        time.sleep(delay)
                        continue
                if exc.code in {401, 403}:
                    raise HevyApiError(
                        "Hevy rejected the API key. Confirm HEVY_API_KEY in the project .env and that the account has Hevy Pro."
                    ) from exc
                raise HevyApiError(f"Hevy API returned HTTP {exc.code} for {path}: {body}") from exc
            except URLError as exc:
                if attempt < 3:
                    time.sleep(attempt * 2.0)
                    continue
                raise HevyApiError(f"Could not connect to Hevy API at {self.base_url}: {exc.reason}") from exc
            except json.JSONDecodeError as exc:
                raise HevyApiError(f"Hevy API returned invalid JSON for {path}.") from exc

        raise HevyApiError(f"Hevy API request failed for {path}.")

    def get_all_workouts(self, page_size: int = 10) -> tuple[list[dict[str, Any]], int]:
        workouts: list[dict[str, Any]] = []
        page = 1
        page_count = 1
        while page <= page_count:
            payload = self.get("/v1/workouts", {"page": page, "pageSize": page_size})
            page_count = max(1, int(payload.get("page_count") or 1))
            page_workouts = payload.get("workouts") or []
            if not isinstance(page_workouts, list):
                raise HevyApiError("Unexpected Hevy response: 'workouts' is not a list.")
            workouts.extend(item for item in page_workouts if isinstance(item, dict))
            print(f"Hevy workouts: page {page}/{page_count} ({len(workouts)} downloaded)")
            page += 1
        return workouts, page_count

    def get_incremental_workouts(
        self, existing: list[dict[str, Any]], expected_count: int, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int, int]:
        known = {str(item["id"]): item for item in existing if isinstance(item, dict) and item.get("id")}
        if len(known) != len(existing) or len(known) > expected_count:
            workouts, pages = self.get_all_workouts(page_size)
            return workouts, pages, len(workouts)

        merged = dict(known)
        page = 1
        page_count = 1
        downloaded = 0
        while page <= page_count:
            payload = self.get("/v1/workouts", {"page": page, "pageSize": page_size})
            page_count = max(1, int(payload.get("page_count") or 1))
            rows = payload.get("workouts")
            if not isinstance(rows, list):
                raise HevyApiError("Unexpected Hevy response: 'workouts' is not a list.")
            downloaded += len(rows)
            for item in rows:
                if isinstance(item, dict) and item.get("id"):
                    merged[str(item["id"])] = item
            print(f"Hevy workouts: page {page}/{page_count} ({downloaded} checked, {len(merged)} total)")
            if len(merged) == expected_count:
                return list(merged.values()), page, downloaded
            if len(merged) > expected_count:
                workouts, pages = self.get_all_workouts(page_size)
                return workouts, pages, len(workouts)
            page += 1
        raise HevyApiError("Hevy account count could not be reconciled with the local snapshot; run a full refresh.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download all Hevy workouts through the official public API.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--incremental", action="store_true", help="Reuse the local snapshot and fetch only pages needed for new workouts.")
    parser.add_argument("--check-config", action="store_true", help="Validate local configuration without calling Hevy.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    api_key = os.environ.get("HEVY_API_KEY", "").strip()
    base_url = (args.base_url or os.environ.get("HEVY_API_BASE_URL") or "https://api.hevyapp.com").strip()

    if not api_key:
        print(f"Missing HEVY_API_KEY. Add it to {Path(args.env_file).resolve()}.", file=sys.stderr)
        return 2
    if not 1 <= args.page_size <= 10:
        print("--page-size must be between 1 and 10.", file=sys.stderr)
        return 2
    if args.check_config:
        print("Hevy configuration is present. API key value was not displayed.")
        return 0

    client = HevyClient(base_url=base_url, api_key=api_key, timeout_seconds=args.timeout_seconds)
    try:
        prior_path = Path(args.output)
        prior = json.loads(prior_path.read_text(encoding="utf-8-sig")) if args.incremental and prior_path.exists() else {}
        user_info = {"data": prior.get("user")} if isinstance(prior, dict) and prior.get("user") else client.get("/v1/user/info")
        count_payload = client.get("/v1/workouts/count")
        expected_count = int(count_payload.get("workout_count") or 0)
        prior_workouts = prior.get("workouts") if isinstance(prior, dict) else None
        if args.incremental and isinstance(prior_workouts, list) and prior_workouts:
            workouts, page_count, downloaded_count = client.get_incremental_workouts(
                prior_workouts, expected_count, page_size=args.page_size
            )
        else:
            workouts, page_count = client.get_all_workouts(page_size=args.page_size)
            downloaded_count = len(workouts)
    except HevyApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    workouts_by_id = {str(item.get("id")): item for item in workouts if item.get("id")}
    workouts_without_id = [item for item in workouts if not item.get("id")]
    unique_workouts = list(workouts_by_id.values()) + workouts_without_id
    unique_workouts.sort(key=lambda item: str(item.get("start_time") or ""))
    if len(unique_workouts) != expected_count:
        print(
            "Downloaded workout count differs from /v1/workouts/count; existing snapshot was left unchanged.",
            file=sys.stderr,
        )
        return 1

    payload = {
        "source": "hevy_public_api",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "api_base_url": base_url,
        "endpoint": "/v1/workouts",
        "user": user_info.get("data") if isinstance(user_info, dict) else None,
        "expected_workout_count": expected_count,
        "downloaded_workout_count": len(unique_workouts),
        "fetched_workout_count": downloaded_count,
        "sync_mode": "incremental" if args.incremental else "full",
        "page_count": page_count,
        "workouts": unique_workouts,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive_path = None
    if not args.no_archive:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = output.parent / f"hevy_workouts_full_{stamp}.json"
        if archive_path.resolve() != output.resolve():
            shutil.copy2(output, archive_path)

    print(f"Hevy workouts fetched this run: {downloaded_count}; consolidated total: {len(unique_workouts)}")
    print(f"Latest snapshot: {output.resolve()}")
    if archive_path:
        print(f"Archived snapshot: {archive_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
