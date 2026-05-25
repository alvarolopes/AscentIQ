from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from common import ANALYSIS_DIR, format_duration, save_json, slugify, utc_timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lê um GPX e gera um resumo de distância e altimetria."
    )
    parser.add_argument("gpx_path", help="Caminho para o arquivo GPX.")
    parser.add_argument(
        "--category",
        choices=("race", "training"),
        default="training",
        help="Define a pasta padrão de saída em analysis/.",
    )
    parser.add_argument("--output", help="Caminho opcional para o JSON de saída.")
    parser.add_argument(
        "--elevation-threshold",
        type=float,
        default=0.5,
        help="Limiar vertical em metros. Para GPX oficial de percurso, 0.5 tende a refletir melhor o D+.",
    )
    return parser.parse_args()


def local_name(tag: str) -> str:
    return tag.split("}")[-1]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def load_points(gpx_path: Path) -> list[dict[str, Any]]:
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    points: list[dict[str, Any]] = []

    for element in root.iter():
        if local_name(element.tag) not in {"trkpt", "rtept"}:
            continue

        lat = element.attrib.get("lat")
        lon = element.attrib.get("lon")
        if lat is None or lon is None:
            continue

        ele = None
        timestamp = None
        for child in element:
            child_name = local_name(child.tag)
            if child_name == "ele" and child.text:
                ele = float(child.text)
            elif child_name == "time":
                timestamp = parse_time(child.text)

        points.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "ele": ele,
                "time": timestamp,
            }
        )

    if len(points) < 2:
        raise ValueError("O GPX precisa ter ao menos dois pontos com latitude/longitude.")

    return points


def summarize_points(points: list[dict[str, Any]], elevation_threshold: float) -> dict[str, Any]:
    distance_m = 0.0
    elevation_gain_m = 0.0
    elevation_loss_m = 0.0

    elevations = [point["ele"] for point in points if point["ele"] is not None]
    times = [point["time"] for point in points if point["time"] is not None]

    for previous, current in zip(points, points[1:]):
        distance_m += haversine_distance_m(
            previous["lat"],
            previous["lon"],
            current["lat"],
            current["lon"],
        )

        if previous["ele"] is None or current["ele"] is None:
            continue

        delta_ele = current["ele"] - previous["ele"]
        if delta_ele >= elevation_threshold:
            elevation_gain_m += delta_ele
        elif delta_ele <= -elevation_threshold:
            elevation_loss_m += abs(delta_ele)

    duration_seconds = None
    if len(times) >= 2:
        candidate_duration = int((max(times) - min(times)).total_seconds())
        if 0 < candidate_duration < 172800:
            duration_seconds = candidate_duration

    return {
        "track_point_count": len(points),
        "distance_km": round(distance_m / 1000, 3),
        "elevation_gain_m": round(elevation_gain_m, 1),
        "elevation_loss_m": round(elevation_loss_m, 1),
        "elevation_min_m": round(min(elevations), 1) if elevations else None,
        "elevation_max_m": round(max(elevations), 1) if elevations else None,
        "duration_seconds": duration_seconds,
        "duration": format_duration(duration_seconds),
    }


def default_output_path(gpx_path: Path, category: str) -> Path:
    bucket = "races" if category == "race" else "trainings"
    return ANALYSIS_DIR / bucket / f"{slugify(gpx_path.stem)}_gpx_analysis.json"


def main() -> int:
    args = parse_args()
    gpx_path = Path(args.gpx_path)
    if not gpx_path.exists():
        raise FileNotFoundError(f"Arquivo GPX não encontrado: {gpx_path}")

    points = load_points(gpx_path)
    summary = summarize_points(points, args.elevation_threshold)

    payload = {
        "analysis_type": "gpx_summary",
        "generated_at_utc": utc_timestamp(),
        "source_file": str(gpx_path.resolve()),
        "category": args.category,
        "source_priority": "official_gpx",
        **summary,
    }

    output_path = Path(args.output) if args.output else default_output_path(gpx_path, args.category)
    save_json(payload, output_path)

    print(f"GPX analisado: {gpx_path.name}")
    print(f"Distância: {payload['distance_km']} km")
    print(f"D+: {payload['elevation_gain_m']} m | D-: {payload['elevation_loss_m']} m")
    if payload["elevation_min_m"] is not None and payload["elevation_max_m"] is not None:
        print(
            f"Faixa de elevação: {payload['elevation_min_m']} m a {payload['elevation_max_m']} m"
        )
    if payload["duration"]:
        print(f"Duração registrada: {payload['duration']}")
    print(f"Saída: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
