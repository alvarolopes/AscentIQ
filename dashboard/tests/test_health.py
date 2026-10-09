"""Synthetic acceptance cases for personal memory, energy and adaptation."""

import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from dashboard.health import ConflictError, HealthStore, _today


class Diary:
    def __init__(self):
        self.days = {}

    def meal(self, day, kcal=2400, complete=True, extra=None):
        self.days[day.isoformat()] = {
            "entries": [
                {
                    "id": "meal-" + day.isoformat(),
                    "text": "Refeição sintética",
                    "analysis": {
                        "items": [
                            {
                                "name": "Alimentos de exemplo",
                                "kcal": kcal,
                                "protein_g": 100,
                                "carbs_g": 250,
                                "fat_g": 80,
                            }
                        ]
                    },
                }
            ],
            "completeness": "complete" if complete else "partial",
            "fasting_declared": False,
            **(extra or {}),
        }

    def read(self, day):
        return copy.deepcopy(
            self.days.get(day.isoformat(), {"entries": [], "completeness": "empty", "fasting_declared": False})
        )

    def read_many(self, days):
        return {day: self.read(day) for day in days}


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.store = HealthStore(self.runtime, self.root)
        self.diary = Diary()
        self.day = _today()

    def tearDown(self):
        self.temp.cleanup()

    def profile(self, start=None):
        effective = (start or self.day - timedelta(days=30)).isoformat()
        self.store.update(
            "profile",
            {
                "name": "Pessoa sintética",
                "age": 42,
                "height_cm": 180,
                "sex": "male",
                "weight_kg": 80,
                "effective_from": effective,
            },
        )
        self.store.update("preferences", {"activity_factor": 1.55, "effective_from": effective})

    def goal(self, **extra):
        self.store.save(
            "goals",
            {
                "id": "goal",
                "type": "fat_loss",
                "description": "Reduzir gordura preservando desempenho",
                "priority": 1,
                "target_kcal": 2400,
                "effective_from": (self.day - timedelta(days=30)).isoformat(),
                **extra,
            },
        )

    def enough_data(self, kcal=2400, slope=0):
        self.profile()
        self.goal()
        for offset in range(14):
            self.diary.meal(self.day - timedelta(days=offset), kcal=kcal)
        for offset in (13, 9, 5, 0):
            self.store.save(
                "measurements",
                {
                    "id": "weight-" + str(offset),
                    "date": (self.day - timedelta(days=offset)).isoformat(),
                    "weight_kg": 80 + (13 - offset) / 7 * slope,
                },
            )

    def test_a14_total_includes_exercise_without_duplicate(self):
        selected = self.day - timedelta(days=1)
        self.diary.meal(selected, 2200)
        self.store.save(
            "energy_records",
            {
                "id": "energy",
                "date": selected.isoformat(),
                "total_kcal": 2800,
                "active_kcal": 800,
                "exercise_kcal": 500,
                "coverage": "full",
                "coverage_hours": 24,
            },
        )
        energy = self.store.summary(selected, {}, self.diary)["energy"]
        self.assertEqual(energy["expenditure_kcal"], 2800)
        self.assertEqual(energy["deficit_kcal"], 600)
        self.assertEqual(energy["balance_kcal"], -600)
        self.assertEqual(energy["components"]["active_kcal"], 800)

    def test_missing_partial_and_pending_intake_do_not_prove_deficit(self):
        selected = self.day - timedelta(days=1)
        self.store.save("energy_records", {"date": selected.isoformat(), "total_kcal": 2800, "coverage": "full"})
        empty = self.store.summary(selected, {}, self.diary)["energy"]
        self.assertIsNone(empty["intake_kcal"])
        self.assertIsNone(empty["deficit_kcal"])
        self.diary.meal(selected, 700, complete=False)
        partial = self.store.summary(selected, {}, self.diary)["energy"]
        self.assertEqual(partial["registered_kcal"], 700)
        self.assertIsNone(partial["deficit_kcal"])
        self.diary.meal(selected, None, complete=True)
        pending = self.store.summary(selected, {}, self.diary)["energy"]
        self.assertEqual(pending["calorie_status"], "pending")
        self.assertIsNone(pending["intake_kcal"])
        self.assertIsNone(pending["deficit_kcal"])
        self.diary.days[selected.isoformat()] = {"entries": [], "completeness": "complete", "fasting_declared": True}
        fasting = self.store.summary(selected, {}, self.diary)["energy"]
        self.assertEqual(fasting["intake_kcal"], 0)
        self.assertEqual(fasting["deficit_kcal"], 2800)

    def test_a34_partial_wearable_not_completed_by_hidden_model(self):
        self.profile()
        self.store.update(
            "preferences", {"energy_method": "wearable", "effective_from": (self.day - timedelta(days=30)).isoformat()}
        )
        selected = self.day - timedelta(days=1)
        self.diary.meal(selected, 2200)
        snapshot = {
            "daily_energy": {
                "daily": [
                    {
                        "date": selected.isoformat(),
                        "total_kcal": 1800,
                        "source": "garmin",
                        "coverage": "complete",
                        "coverage_hours": 12,
                    }
                ]
            }
        }
        energy = self.store.summary(selected, snapshot, self.diary)["energy"]
        self.assertEqual(energy["source"], "garmin")
        self.assertEqual(energy["coverage"], "partial")
        self.assertEqual(energy["expenditure_kcal"], 1800)
        self.assertIsNone(energy["deficit_kcal"])

    def test_partial_wearable_uses_identified_integral_model_in_auto(self):
        self.profile()
        selected = self.day - timedelta(days=1)
        self.diary.meal(selected, 2200)
        snapshot = {
            "daily_energy": {
                "daily": [
                    {
                        "date": selected.isoformat(),
                        "total_kcal": 1800,
                        "active_kcal": 300,
                        "source": "garmin",
                        "coverage": "unknown",
                        "method": "wearable_total",
                    }
                ]
            }
        }
        energy = self.store.summary(selected, snapshot, self.diary)["energy"]
        self.assertEqual(energy["source"], "profile_model")
        self.assertEqual(energy["coverage_basis"], "modeled_full_day")
        self.assertIsNone(energy["observed_hours"])
        self.assertTrue(energy["usable"])
        self.assertEqual(energy["deficit_kcal"], energy["expenditure_kcal"] - 2200)
        self.assertEqual(energy["alternatives"][0]["source"], "garmin")
        self.assertEqual(energy["alternatives"][0]["coverage"], "unknown")
        self.assertEqual(energy["alternatives"][0]["total_kcal"], 1800)
        self.assertIn("modelo integral", " ".join(energy["limitations"]))
        snapshot["daily_energy"]["daily"][0]["date"] = self.day.isoformat()
        self.diary.meal(self.day, 2200)
        current = self.store.summary(self.day, snapshot, self.diary)["energy"]
        self.assertEqual(current["source"], "profile_model")
        self.assertTrue(current["is_projection"])
        self.assertIsNone(current["deficit_kcal"])

    def test_explicit_model_choice_and_full_provider_precedence(self):
        self.profile()
        selected = self.day - timedelta(days=1)
        self.diary.meal(selected, 2200)
        snapshot = {
            "daily_energy": [
                {"date": selected.isoformat(), "total_kcal": 2800, "source": "garmin", "coverage": "complete"}
            ]
        }
        self.assertEqual(self.store.summary(selected, snapshot, self.diary)["energy"]["source"], "garmin")
        self.store.update(
            "preferences", {"energy_method": "model", "effective_from": (self.day - timedelta(days=30)).isoformat()}
        )
        energy = self.store.summary(selected, snapshot, self.diary)["energy"]
        self.assertEqual(energy["source"], "profile_model")
        self.assertEqual(energy["alternatives"][0]["total_kcal"], 2800)
        with self.assertRaises(ValueError):
            self.store.update("preferences", {"energy_method": "magic"})

    def test_provider_file_read_without_local_personal_data(self):
        import json

        selected = self.day - timedelta(days=1)
        (self.root / "data").mkdir()
        (self.root / "data" / "daily_energy.json").write_text(
            json.dumps(
                {
                    "daily": [
                        {"date": selected.isoformat(), "total_kcal": 2800, "source": "garmin", "coverage": "complete"}
                    ]
                }
            )
        )
        self.diary.meal(selected, 2200)
        self.assertEqual(self.store.summary(selected, {}, self.diary)["energy"]["deficit_kcal"], 600)

    def test_a21_insufficient_evidence_preserves_plan(self):
        self.profile()
        self.goal()
        self.diary.meal(self.day)
        before = self.store.read()["plans"]
        result = self.store.review(self.day, {}, self.diary)
        self.assertEqual(result["proposal"]["action"], "collect_data")
        self.assertEqual(result["proposal"]["delta_kcal"], 0)
        self.assertEqual(self.store.read()["plans"], before)
        self.store.decide(result["proposal"]["id"], "accept", self.day, {}, self.diary)
        self.assertEqual(self.store.read()["plans"], before)

    def test_a35_empty_installation_initial_and_provisional_plan(self):
        self.assertEqual(self.store.read()["revision"], 0)
        self.goal(target_kcal=None, effective_from=self.day.isoformat())
        provisional = self.store.summary(self.day, {}, self.diary)["active_plan"]
        self.assertEqual(provisional["status"], "provisional")
        self.assertIsNone(provisional["target_kcal"])
        self.profile(start=self.day)
        plan = self.store.summary(self.day, {}, self.diary)["active_plan"]
        self.assertEqual(plan["status"], "active")
        self.assertGreater(plan["target_kcal"], 2000)
        self.assertIn("mifflin", plan["method"])
        self.assertGreater(plan["version"], provisional["version"])
        self.assertIn("next_review_date", plan)
        self.assertEqual(len(self.store.read()["plans"]), 2)

    def test_a36_trend_adjustment_requires_acceptance_and_preserves_history(self):
        self.enough_data()
        current = self.store.summary(self.day, {}, self.diary)["active_plan"]
        result = self.store.review(self.day, {}, self.diary)
        proposal = result["proposal"]
        self.assertEqual(proposal["action"], "adjust")
        self.assertEqual(proposal["delta_kcal"], -100)
        self.assertEqual(proposal["suggested_plan"]["target_kcal"], 2300)
        self.assertEqual(self.store.summary(self.day, {}, self.diary)["active_plan"]["target_kcal"], 2400)
        revision_before = result["state"]["revision"]
        accepted = self.store.decide(proposal["id"], "accepted", self.day, {}, self.diary)
        next_day = self.day + timedelta(days=1)
        self.assertEqual(self.store.summary(next_day, {}, self.diary)["active_plan"]["target_kcal"], 2300)
        self.assertEqual(self.store.summary(self.day, {}, self.diary)["active_plan"]["target_kcal"], 2400)
        self.assertEqual(self.store.read(revision_before)["plans"][0]["target_kcal"], 2400)
        self.assertEqual(accepted["decision"]["previous_plan_id"], current["id"])
        repeat = self.store.decide(proposal["id"], "accepted", self.day, {}, self.diary)
        self.assertEqual(repeat["state"]["revision"], accepted["state"]["revision"])
        next_review = self.day + timedelta(days=8)
        for offset in range(1, 9):
            self.diary.meal(self.day + timedelta(days=offset), 2300)
        for offset in (1, 3, 5, 8):
            self.store.save(
                "measurements",
                {"date": (self.day + timedelta(days=offset)).isoformat(), "weight_kg": 80 - offset * 0.25 / 7},
            )
        followup = self.store.review(next_review, {}, self.diary)["proposal"]
        self.assertEqual(followup["previous_plan"]["target_kcal"], 2300)
        self.assertTrue(followup["evidence"]["previous_decisions"])

    def test_a37_food_or_goal_change_marks_proposal_stale(self):
        self.enough_data()
        result = self.store.review(self.day, {}, self.diary)
        proposal = result["proposal"]
        self.diary.days[self.day.isoformat()]["entries"][0]["analysis"]["items"][0]["kcal"] = 2350
        with self.assertRaises(ConflictError):
            self.store.decide(proposal["id"], "accepted", self.day, {}, self.diary)
        saved = self.store.read()
        self.assertEqual(saved["proposals"][0]["status"], "stale")
        self.assertEqual(len(saved["plans"]), 1)
        fresh = self.store.review(self.day, {}, self.diary)["proposal"]
        self.store.save("goals", {**saved["goals"][0], "desired_weekly_change_kg": -0.1})
        with self.assertRaises(ConflictError):
            self.store.decide(fresh["id"], "accepted", self.day, {}, self.diary)

    def test_recovery_or_competing_goal_prevents_restriction(self):
        self.enough_data()
        for offset in (0, 1):
            self.store.save("checkins", {"date": (self.day - timedelta(days=offset)).isoformat(), "fatigue": 8})
        result = self.store.review(self.day, {}, self.diary)["proposal"]
        self.assertEqual(result["action"], "maintain")
        self.assertEqual(result["delta_kcal"], 0)
        self.assertIn("recuperação", result["reason"])

    def test_rejection_does_not_publish_plan_and_same_review_is_idempotent(self):
        self.enough_data()
        first = self.store.review(self.day, {}, self.diary)
        repeated = self.store.review(self.day, {}, self.diary)
        self.assertEqual(first["state"]["revision"], repeated["state"]["revision"])
        self.store.decide(first["proposal"]["id"], "reject", self.day, {}, self.diary)
        self.assertEqual(len(self.store.read()["plans"]), 1)
        self.assertEqual(self.store.read()["decisions"][0]["decision"], "rejected")

    def test_versioned_profile_not_used_before_effective_date(self):
        self.profile(start=self.day)
        self.diary.meal(self.day - timedelta(days=1))
        past = self.store.summary(self.day - timedelta(days=1), {}, self.diary)["energy"]
        self.assertIsNone(past["expenditure_kcal"])
        now = self.store.summary(self.day, {}, self.diary)["energy"]
        self.assertEqual(now["source"], "profile_model")
        self.assertTrue(now["is_projection"])

    def test_goal_archive_edit_and_remove_preserve_historical_versions(self):
        self.goal()
        yesterday = self.day - timedelta(days=1)
        before = self.store.summary(yesterday, {}, self.diary)
        self.assertEqual(before["active_goal"]["description"], "Reduzir gordura preservando desempenho")
        self.store.save(
            "goals", {"id": "goal", "type": "fat_loss", "description": "Objetivo concluído", "status": "completed"}
        )
        self.assertIsNone(self.store.summary(self.day, {}, self.diary)["active_goal"])
        past = self.store.summary(yesterday, {}, self.diary)
        self.assertEqual(past["active_goal"]["description"], before["active_goal"]["description"])
        self.assertEqual(past["active_plan"]["target_kcal"], 2400)
        self.store.remove("goals", "goal")
        self.assertEqual(self.store.summary(self.day, {}, self.diary)["goals"], [])
        self.assertEqual(self.store.summary(yesterday, {}, self.diary)["active_goal"]["id"], "goal")

    def test_historical_proposal_cannot_apply_to_new_current_goal(self):
        self.profile()
        self.goal()
        yesterday = self.day - timedelta(days=1)
        reviewed = self.store.review(yesterday, {}, self.diary)["proposal"]
        self.store.save("goals", {"id": "goal", "type": "fat_loss", "description": "Concluído", "status": "completed"})
        with self.assertRaises(ConflictError):
            self.store.decide(reviewed["id"], "accepted", yesterday, {}, self.diary)
        self.assertEqual(self.store.read()["proposals"][0]["status"], "stale")

    def test_legacy_seed_preserves_current_references_and_actual_measurement_date(self):
        import json

        (self.root / "data").mkdir()
        reference = (self.day - timedelta(days=20)).isoformat()
        (self.root / "data" / "athlete_profile.json").write_text(
            json.dumps(
                {
                    "name": "Pessoa legada sintética",
                    "age": 42,
                    "height_cm": 180,
                    "sex": "male",
                    "weight_kg": 85,
                    "private_unused_field": "not adopted",
                }
            )
        )
        (self.root / "data" / "athlete_preferences.json").write_text(
            json.dumps(
                {"activity_factor": 1.55, "equipment": ["Equipamento sintético"], "provider_password": "not adopted"}
            )
        )
        snapshot = {
            "athlete": {},
            "body": {"reference_date": reference, "current": {"weight_kg": 80, "body_fat_pct": 20}},
            "goals": {
                "health": {
                    "description": "Meta atual sintética",
                    "type": "fat_loss",
                    "status": "active",
                    "target_kcal": 2400,
                },
                "endurance": {"name": "Evento concluído sintético", "status": "completed"},
            },
        }
        imported = self.store.seed_legacy(snapshot)
        self.assertEqual(imported["revision"], 1)
        self.assertTrue(imported["legacy_imported"])
        self.assertEqual(imported["profile"]["weight_kg"], 80)
        self.assertEqual(imported["profile"]["source"], "legacy_reference")
        self.assertEqual(imported["measurements"][0]["date"], reference)
        self.assertNotIn("private_unused_field", imported["profile"])
        self.assertNotIn("provider_password", imported["preferences"])
        self.assertEqual(imported["goals"][0]["priority"], 1)
        self.assertEqual(imported["goals"][1]["status"], "completed")
        self.assertEqual(len(imported["plans"]), 1)
        self.assertEqual(imported["plans"][0]["target_kcal"], 2400)
        repeated = self.store.seed_legacy(snapshot)
        self.assertEqual(repeated["revision"], 1)
        self.assertEqual(repeated["goals"], imported["goals"])

    def test_legacy_empty_and_unrecognized_shapes_do_not_create_facts(self):
        empty = self.store.seed_legacy({})
        self.assertEqual(empty["revision"], 0)
        self.assertNotIn("legacy_imported", empty)
        self.assertEqual(
            self.store.seed_legacy({"goals": {"health": ["historical list"], "endurance": {"unknown": 49}}})[
                "revision"
            ],
            0,
        )
        self.store.update("profile", {"name": "Pessoa informada"})
        skipped = self.store.seed_legacy(
            {"athlete": {"name": "Referência diferente"}, "goals": {"health": "Não substituir"}}
        )
        self.assertEqual(skipped["profile"]["name"], "Pessoa informada")
        self.assertEqual(skipped["goals"], [])

    def test_legacy_no_numeric_target_inferred_and_failed_seed_is_atomic(self):
        import json

        (self.root / "data").mkdir()
        (self.root / "data" / "athlete_profile.json").write_text(
            json.dumps({"age": 42, "height_cm": 180, "sex": "male", "weight_kg": 80})
        )
        (self.root / "data" / "athlete_preferences.json").write_text(json.dumps({"activity_factor": 1.55}))
        snapshot = {"goals": {"health": {"description": "Meta atual sem alvo declarado", "type": "fat_loss"}}}
        with patch("dashboard.health._initial_plan", side_effect=RuntimeError("interrupted synthetic seed")):
            with self.assertRaises(RuntimeError):
                self.store.seed_legacy(snapshot)
        self.assertEqual(self.store.read()["revision"], 0)
        self.assertEqual(self.store.read()["profile"], {})
        seeded = self.store.seed_legacy(snapshot)
        self.assertIsNone(seeded["plans"][0]["target_kcal"])
        self.assertEqual(seeded["plans"][0]["status"], "provisional")
        self.assertNotIn("target_kcal", seeded["goals"][0])

    def test_weight_gain_without_declared_target_is_provisional(self):
        self.profile()
        self.goal(type="weight_gain", target_kcal=None)
        summary = self.store.summary(self.day, {}, self.diary)
        self.assertIsNone(summary["active_plan"]["target_kcal"])
        self.assertEqual(summary["active_plan"]["status"], "provisional")
        self.assertEqual(self.store.review(self.day, {}, self.diary)["proposal"]["action"], "collect_data")

    def test_concurrent_stale_clients_cannot_lose_updates(self):
        revision = self.store.read()["revision"]

        def write(name):
            try:
                return self.store.update("profile", {"name": name}, revision)
            except ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ("Pessoa A", "Pessoa B")))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.store.read()["revision"], revision + 1)
        self.assertEqual(HealthStore(self.runtime, self.root).read()["revision"], revision + 1)

    def test_validation_blocks_nonfinite_and_bad_dates(self):
        for bad in (float("nan"), float("inf"), -1, True, "80"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.store.save("measurements", {"date": self.day.isoformat(), "weight_kg": bad})
        with self.assertRaises(ValueError):
            self.store.save("energy_records", {"date": "not-a-date", "total_kcal": 2000})
        with self.assertRaises(ValueError):
            self.store.save("energy_records", {"date": self.day.isoformat(), "active_kcal": 500})
        self.assertEqual(self.store.read()["revision"], 0)


if __name__ == "__main__":
    unittest.main()
