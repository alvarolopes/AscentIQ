"""Synthetic coverage inference, recent wearable reference and calibration."""

import unittest
from datetime import date, timedelta

from dashboard.wearable_energy import calibrate, infer_coverage, recent_reference, with_inferred_coverage


def row(day, total=2700, **extra):
    return {"date": day.isoformat(), "source": "garmin", "total_kcal": total, "resting_kcal": 1900, **extra}


class InferCoverageTests(unittest.TestCase):
    def test_observation_after_the_day_is_complete(self):
        self.assertEqual(
            infer_coverage("2026-10-08", "2026-10-09T08:12:00-03:00"),
            ("complete", 24.0),
        )

    def test_same_day_observation_is_partial_with_elapsed_hours(self):
        coverage, hours = infer_coverage("2026-10-08", "2026-10-08T15:03:58-03:00", "2026-10-08T00:00:00")
        self.assertEqual(coverage, "partial")
        assert hours is not None
        self.assertAlmostEqual(hours, 15.1, places=1)
        coverage, hours = infer_coverage("2026-10-08", "2026-10-08T12:30:00")
        self.assertEqual((coverage, hours), ("partial", 12.5))

    def test_missing_or_earlier_observation_stays_unknown(self):
        self.assertEqual(infer_coverage("2026-10-08", None), ("unknown", None))
        self.assertEqual(
            infer_coverage("2026-10-08", "2026-10-07T22:00:00-03:00"),
            ("unknown", None),
        )

    def test_explicit_coverage_is_never_overwritten(self):
        explicit = row(date(2026, 10, 8), coverage="partial", coverage_hours=10, observed_at="2026-10-09T08:00:00")
        self.assertIs(with_inferred_coverage(explicit), explicit)
        unknown = row(date(2026, 10, 8), coverage="unknown", observed_at="2026-10-09T08:00:00")
        inferred = with_inferred_coverage(unknown)
        self.assertEqual((inferred["coverage"], inferred["coverage_hours"]), ("complete", 24.0))
        self.assertEqual(inferred["coverage_basis"], "inferred_from_observation_time")
        self.assertEqual(unknown["coverage"], "unknown")


class RecentReferenceTests(unittest.TestCase):
    def test_mean_median_and_window_exclude_the_day_itself(self):
        today = date(2026, 10, 15)
        rows = [
            row(today - timedelta(days=offset), total=2000 + offset * 100, coverage="complete")
            for offset in range(1, 11)
        ]
        rows.append(row(today, total=9999, coverage="complete"))
        reference = recent_reference(rows, today)
        assert reference is not None
        self.assertEqual(reference["days_used"], 10)
        self.assertEqual(reference["total_kcal"], round(sum(2000 + o * 100 for o in range(1, 11)) / 10))
        self.assertEqual(reference["median_kcal"], 2550)
        self.assertEqual((reference["min_kcal"], reference["max_kcal"]), (2100, 3000))
        self.assertEqual(reference["resting_kcal"], 1900)
        self.assertEqual(reference["source"], "garmin_recent_mean")
        self.assertEqual(reference["method"], "wearable_recent_mean_14d_v1")
        self.assertEqual((reference["window_start"], reference["window_end"]), ("2026-10-01", "2026-10-14"))
        self.assertTrue(any("estimativa do dispositivo" in text for text in reference["assumptions"]))

    def test_partial_and_unknown_days_do_not_count_and_few_days_return_none(self):
        today = date(2026, 10, 15)
        rows = [row(today - timedelta(days=o), coverage="complete") for o in range(1, 7)]
        rows.append(row(today - timedelta(days=7), coverage="partial", coverage_hours=12))
        rows.append(row(today - timedelta(days=8), coverage="unknown"))
        self.assertIsNone(recent_reference(rows, today))
        rows.append(row(today - timedelta(days=9), coverage="complete", total=2800))
        reference = recent_reference(rows, today)
        assert reference is not None
        self.assertEqual(reference["days_used"], 7)
        self.assertEqual(reference["total_kcal"], round((6 * 2700 + 2800) / 7))

    def test_inferred_rows_count_and_last_row_per_date_wins(self):
        today = date(2026, 10, 15)
        rows = [row(today - timedelta(days=o), coverage="complete") for o in range(1, 8)]
        rows.append(row(today - timedelta(days=1), coverage="complete", total=5000))
        reference = recent_reference(rows, today)
        assert reference is not None
        self.assertEqual(reference["days_used"], 7)
        self.assertEqual(reference["total_kcal"], round((6 * 2700 + 5000) / 7))
        inferred = [
            row(
                today - timedelta(days=o),
                coverage="unknown",
                observed_at=(today - timedelta(days=o - 1)).isoformat() + "T08:00:00-03:00",
            )
            for o in range(1, 8)
        ]
        reference = recent_reference(inferred, today)
        assert reference is not None
        self.assertEqual(reference["days_used"], 7)


class CalibrateTests(unittest.TestCase):
    def test_insufficient_reports_exactly_what_is_missing(self):
        result = calibrate(2700, [{"usable": True, "intake_kcal": 2400}], [{"date": "2026-10-01", "weight_kg": 80}])
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["required"], {"usable_days": 10, "weight_points": 4, "weight_span_days": 14})
        self.assertEqual((result["usable_days"], result["weight_points"], result["weight_span_days"]), (1, 1, 0))
        text = "; ".join(result["missing"])
        self.assertIn("10 dias completos", text)
        self.assertIn("4 medidas de peso", text)
        self.assertIn("14 dias", text)

    def test_applied_calibration_uses_intake_and_weight_trend(self):
        series = [{"usable": True, "intake_kcal": 2400, "expenditure_kcal": 2675} for _ in range(12)]
        start = date(2026, 9, 20)
        weights = [{"date": (start + timedelta(days=7 * i)).isoformat(), "weight_kg": 80 - 0.25 * i} for i in range(4)]
        result = calibrate(2600, series, weights)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["weekly_change_kg"], -0.25)
        self.assertEqual(result["implied_tdee_kcal"], 2675)
        self.assertEqual((result["calibrated_kcal"], result["shift_kcal"]), (2675, 75))
        self.assertFalse(result["clamped"])
        self.assertEqual(result["method"], "intake_weight_trend_calibration_v1")

    def test_shift_is_clamped_to_fifteen_percent(self):
        series = [{"usable": True, "intake_kcal": 2400, "expenditure_kcal": 2000} for _ in range(12)]
        start = date(2026, 9, 20)
        weights = [{"date": (start + timedelta(days=7 * i)).isoformat(), "weight_kg": 80 + 2 * i} for i in range(4)]
        result = calibrate(2000, series, weights)
        self.assertEqual(result["status"], "applied")
        self.assertTrue(result["clamped"])
        self.assertEqual(result["shift_kcal"], -300)
        self.assertEqual(result["calibrated_kcal"], 1700)


if __name__ == "__main__":
    unittest.main()
