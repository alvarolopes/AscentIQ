from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from statistics import mean
from typing import Any

import fitdecode


def fmt_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    total_seconds = int(round(seconds_per_km))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}/km"


def load_fit_messages(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    laps: list[dict[str, Any]] = []
    session: dict[str, Any] | None = None

    opener = gzip.open if path.suffix.lower() == '.gz' else open
    with opener(path, 'rb') as f:
        with fitdecode.FitReader(f) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                fields = {field.name: field.value for field in frame.fields}
                if frame.name == 'lap':
                    laps.append(fields)
                elif frame.name == 'session':
                    session = fields

    return laps, session


def summarize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cumulative_km = 0.0
    for index, lap in enumerate(laps, start=1):
        distance_km = (lap.get('total_distance') or 0.0) / 1000
        timer_s = float(lap.get('total_timer_time') or 0.0)
        elapsed_s = float(lap.get('total_elapsed_time') or 0.0)
        pace_s_per_km = (timer_s / distance_km) if distance_km else None
        cumulative_km += distance_km
        items.append(
            {
                'lap_index': index,
                'distance_km': round(distance_km, 3),
                'cumulative_km': round(cumulative_km, 3),
                'timer_s': round(timer_s, 3),
                'elapsed_s': round(elapsed_s, 3),
                'pace_s_per_km': round(pace_s_per_km, 1) if pace_s_per_km is not None else None,
                'pace_avg': fmt_pace(pace_s_per_km),
                'ascent_m': int(lap.get('total_ascent') or 0),
                'descent_m': int(lap.get('total_descent') or 0),
                'avg_hr': lap.get('avg_heart_rate'),
                'max_hr': lap.get('max_heart_rate'),
                'avg_power': lap.get('avg_power'),
                'avg_running_cadence': lap.get('avg_running_cadence'),
                'altitude_min_m': round(float(lap.get('enhanced_min_altitude') or 0.0), 1),
                'altitude_max_m': round(float(lap.get('enhanced_max_altitude') or 0.0), 1),
            }
        )
    return items


def summarize_section(name: str, laps: list[dict[str, Any]]) -> dict[str, Any]:
    distance = sum(item['distance_km'] for item in laps)
    timer_s = sum(item['timer_s'] for item in laps)
    hr_values = [item['avg_hr'] for item in laps if item['avg_hr'] is not None]
    pace = (timer_s / distance) if distance else None
    return {
        'name': name,
        'distance_km': round(distance, 3),
        'pace_s_per_km': round(pace, 1) if pace is not None else None,
        'pace_avg': fmt_pace(pace),
        'ascent_m': sum(item['ascent_m'] for item in laps),
        'descent_m': sum(item['descent_m'] for item in laps),
        'avg_hr': round(mean(hr_values), 1) if hr_values else None,
    }


def build_payload(path: Path) -> dict[str, Any]:
    raw_laps, session = load_fit_messages(path)
    laps = summarize_laps(raw_laps)

    full_km_laps = [item for item in laps if item['distance_km'] > 0.95]
    final_partial = [item for item in laps if item['distance_km'] <= 0.95]

    sections = {
        'km_1_5': summarize_section('km_1_5', full_km_laps[:5]),
        'km_6_10': summarize_section('km_6_10', full_km_laps[5:10]),
        'km_11_15': summarize_section('km_11_15', full_km_laps[10:15]),
        'km_16_20': summarize_section('km_16_20', full_km_laps[15:20]),
        'km_21_25': summarize_section('km_21_25', full_km_laps[20:25]),
        'last_10_full_km': summarize_section('last_10_full_km', full_km_laps[15:25]),
    }

    fastest = sorted(full_km_laps, key=lambda item: item['pace_s_per_km'])[:5]
    slowest = sorted(full_km_laps, key=lambda item: item['pace_s_per_km'], reverse=True)[:5]

    last_five = sections['km_21_25']
    prior_five = sections['km_16_20']
    last_five_pace_gain_s = None
    if last_five['pace_s_per_km'] and prior_five['pace_s_per_km']:
        last_five_pace_gain_s = round(prior_five['pace_s_per_km'] - last_five['pace_s_per_km'], 1)

    return {
        'source_file': str(path),
        'session': {
            'total_elapsed_time_s': round(float(session.get('total_elapsed_time') or 0.0), 3) if session else None,
            'total_timer_time_s': round(float(session.get('total_timer_time') or 0.0), 3) if session else None,
            'total_distance_km': round((float(session.get('total_distance') or 0.0) / 1000), 3) if session else None,
            'total_ascent_m': int(session.get('total_ascent') or 0) if session else None,
            'total_descent_m': int(session.get('total_descent') or 0) if session else None,
            'avg_hr': session.get('avg_heart_rate') if session else None,
            'max_hr': session.get('max_heart_rate') if session else None,
        },
        'laps': laps,
        'sections': sections,
        'fastest_full_km_laps': fastest,
        'slowest_full_km_laps': slowest,
        'final_partial_lap': final_partial[0] if final_partial else None,
        'key_findings': {
            'last_5k_vs_km_16_20_pace_gain_s_per_km': last_five_pace_gain_s,
            'last_5k_avg_hr': last_five['avg_hr'],
            'km_16_20_avg_hr': prior_five['avg_hr'],
            'final_3_full_km_laps': full_km_laps[22:25],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Parse a FIT or FIT.GZ file and emit lap-level JSON.')
    parser.add_argument('input_path', help='Path to the FIT or FIT.GZ file.')
    parser.add_argument('--output', help='Optional path to the output JSON file.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    payload = build_payload(input_path)
    output_path = Path(args.output) if args.output else input_path.with_suffix('.fit.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
