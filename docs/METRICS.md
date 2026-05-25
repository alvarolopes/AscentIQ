# Metrics Reference

This project focuses on endurance durability and mountain-readiness rather than pace-first road racing.

## Mountain Metrics

- `vertical_per_km`: elevation gain divided by distance. Useful for comparing how mountainous two routes are.
- `vertical_speed`: elevation gain divided by elapsed duration. Useful for long mountain days where total time matters.
- `vertical_speed_moving`: elevation gain divided by moving duration. Useful when separating effort from stopped time.
- `stopped_time`: elapsed time minus moving time. Useful for identifying pauses, aid-station cost, navigation delays, or fatigue breaks.
- `mountain_index`: distance plus elevation gain divided by 100. Useful as a simple route-demand score.

## Cardiovascular Metrics

- `avg_hr`: average heart rate during the activity.
- `max_hr`: maximum observed heart rate.
- `heart_rate_efficiency`: pace in seconds per kilometer divided by average heart rate. Lower values generally mean faster movement per heartbeat, but terrain must always be considered.

## Performance Management Metrics

- `fitness`: chronic load estimate using a 42-day smoothing window.
- `fatigue`: acute load estimate using a 7-day smoothing window.
- `form`: readiness estimate calculated as `fitness - fatigue`.
- `fitness_ramp_rate_7d`: seven-day change in fitness.
- `recovery`: sleep-based readiness signal when sleep data is available.

These metrics are a custom model for this repository. They are not intended to replicate a proprietary platform exactly.

## Coaching Interpretation

For the Arequipa objective, the most important signals are:

- Fitness should trend upward without extreme ramp spikes.
- Fatigue can be negative before hard blocks, but should recover before key events.
- Vertical exposure should appear regularly enough to maintain climbing economy.
- Strong finishes in long trail races are treated as evidence of pacing control and endurance durability.
