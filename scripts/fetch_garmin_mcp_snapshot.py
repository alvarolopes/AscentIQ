from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "garmin_mcp_exports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a local JSON snapshot from a Garmin MCP server."
    )
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD. Defaults to 14 days ago.")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--output", help="Output JSON file. Defaults to data/garmin_mcp_exports/garmin_mcp_snapshot_*.json.")
    parser.add_argument("--server-command", default=os.environ.get("GARMIN_MCP_COMMAND", "uvx"))
    parser.add_argument(
        "--server-arg",
        action="append",
        default=None,
        help="Argument passed to the MCP server command. Can be repeated. Defaults to mcp-garmin.",
    )
    parser.add_argument("--activity-tool", default="get_activities_by_date")
    parser.add_argument("--all-activities", action="store_true", help="Fetch activities with paginated get_activities until empty.")
    parser.add_argument("--activity-page-size", type=int, default=100)
    parser.add_argument("--max-activities", type=int, default=5000)
    parser.add_argument("--sleep-tool", default="get_sleep_data")
    parser.add_argument("--skip-sleep", action="store_true")
    parser.add_argument(
        "--daily-tool",
        action="append",
        default=[],
        help="Extra daily tool to capture for each date, e.g. get_hrv_data. Can be repeated.",
    )
    parser.add_argument(
        "--range-tool",
        action="append",
        default=[],
        help="Tool to capture once with start_date/end_date, e.g. get_weigh_ins. Can be repeated.",
    )
    parser.add_argument(
        "--profile-tool",
        action="append",
        default=["get_user_profile", "get_personal_records"],
        help="Profile-level tool to capture once. Can be repeated.",
    )
    parser.add_argument(
        "--activity-detail-tool",
        action="append",
        default=[],
        help="Activity-level tool to capture with activity_id, e.g. get_activity_splits. Can be repeated.",
    )
    parser.add_argument("--max-detail-activities", type=int, default=0)
    parser.add_argument("--list-tools", action="store_true", help="Only list server tools and write no snapshot.")
    return parser.parse_args()


def date_range(start: date, end: date) -> list[str]:
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def output_path(args: argparse.Namespace, start: str, end: str) -> Path:
    if args.output:
        return Path(args.output)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"garmin_mcp_snapshot_{start}_to_{end}_{stamp}.json"


def decode_tool_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")
    elif hasattr(result, "dict"):
        payload = result.dict()
    else:
        payload = result
    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, list) and len(content) == 1:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    if isinstance(content, list) and len(content) > 1:
        decoded_items: list[Any] = []
        for item in content:
            text = item.get("text") if isinstance(item, dict) else None
            if not text:
                decoded_items.append(item)
                continue
            try:
                decoded_items.append(json.loads(text))
            except json.JSONDecodeError:
                decoded_items.append(text)
        return decoded_items
    return payload


async def call_tool_safely(session: Any, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    try:
        result = await session.call_tool(tool_name, arguments=arguments or {})
        return decode_tool_result(result)
    except Exception as exc:  # Keep snapshots useful even when one Garmin endpoint fails.
        return {"error": str(exc), "tool": tool_name, "arguments": arguments or {}}


async def fetch_all_activities(session: Any, args: argparse.Namespace) -> dict[str, Any]:
    start = 0
    pages: list[Any] = []
    total_items = 0
    while start < args.max_activities:
        payload = await call_tool_safely(
            session,
            "get_activities",
            {"start": start, "limit": args.activity_page_size},
        )
        pages.append({"start": start, "limit": args.activity_page_size, "payload": payload})
        if isinstance(payload, dict) and payload.get("error"):
            break
        items = payload if isinstance(payload, list) else payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            break
        total_items += len(items)
        if len(items) < args.activity_page_size:
            break
        start += args.activity_page_size
    return {"mode": "paginated", "total_items_seen": total_items, "pages": pages}


def walk_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        found.append(payload)
        for value in payload.values():
            found.extend(walk_dicts(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(walk_dicts(item))
    return found


def extract_activity_ids(payload: Any) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for row in walk_dicts(payload):
        for key in ("activityId", "activity_id", "id"):
            value = row.get(key)
            if value is None:
                continue
            try:
                activity_id = int(value)
            except (TypeError, ValueError):
                continue
            if activity_id not in seen:
                seen.add(activity_id)
                ids.append(activity_id)
            break
    return ids


async def fetch_activity_details(session: Any, activities: Any, args: argparse.Namespace) -> dict[str, Any]:
    activity_ids = extract_activity_ids(activities)[: max(args.max_detail_activities, 0)]
    details: dict[str, Any] = {
        "activity_ids": activity_ids,
        "max_detail_activities": args.max_detail_activities,
        "tools": {},
    }
    for tool_name in args.activity_detail_tool:
        details["tools"][tool_name] = []
        for activity_id in activity_ids:
            payload = await call_tool_safely(session, tool_name, {"activity_id": activity_id})
            details["tools"][tool_name].append({"activity_id": activity_id, "payload": payload})
    return details


async def capture(args: argparse.Namespace) -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise SystemExit(
            "Missing MCP Python SDK. Install optional dependencies with: "
            "python -m pip install -r requirements-mcp.txt"
        ) from exc

    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start = date.fromisoformat(args.start_date) if args.start_date else end - timedelta(days=14)
    server_args = args.server_arg if args.server_arg is not None else ["mcp-garmin"]
    env = os.environ.copy()
    params = StdioServerParameters(command=args.server_command, args=server_args, env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            tools = tools_response.model_dump(mode="json") if hasattr(tools_response, "model_dump") else tools_response
            if args.list_tools:
                print(json.dumps(tools, ensure_ascii=False, indent=2))
                return 0

            if args.all_activities:
                activities = await fetch_all_activities(session, args)
            else:
                activities = await call_tool_safely(
                    session,
                    args.activity_tool,
                    {"start_date": start.isoformat(), "end_date": end.isoformat()},
                )
            snapshot: dict[str, Any] = {
                "source": "garmin_mcp",
                "server_command": args.server_command,
                "server_args": server_args,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "date_range": {"start": start.isoformat(), "end": end.isoformat()},
                "activities": activities,
                "activity_details": {},
                "sleep": {"daily": []},
                "daily_metrics": {},
                "range_metrics": {},
                "profile": {},
            }

            if not args.skip_sleep:
                for day in date_range(start, end):
                    sleep_payload = await call_tool_safely(session, args.sleep_tool, {"date": day})
                    snapshot["sleep"]["daily"].append({"date": day, "payload": sleep_payload})

            for tool_name in args.daily_tool:
                snapshot["daily_metrics"][tool_name] = []
                for day in date_range(start, end):
                    payload = await call_tool_safely(session, tool_name, {"date": day})
                    snapshot["daily_metrics"][tool_name].append({"date": day, "payload": payload})

            for tool_name in args.range_tool:
                snapshot["range_metrics"][tool_name] = await call_tool_safely(
                    session,
                    tool_name,
                    {"start_date": start.isoformat(), "end_date": end.isoformat()},
                )

            for tool_name in dict.fromkeys(args.profile_tool):
                snapshot["profile"][tool_name] = await call_tool_safely(session, tool_name)

            if args.activity_detail_tool and args.max_detail_activities > 0:
                snapshot["activity_details"] = await fetch_activity_details(session, activities, args)

    out_path = output_path(args, start.isoformat(), end.isoformat())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    return asyncio.run(capture(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
