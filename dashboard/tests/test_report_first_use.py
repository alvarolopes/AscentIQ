"""Compile real templates against empty and synthetic data, never a real dataset."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from dashboard.pipeline import publish_report, rebuild, training_snapshot
from dashboard.snapshot import ROOT, build_snapshot


@unittest.skipUnless(shutil.which(os.environ.get("TYPST_BIN", "typst")), "Typst is required for report compilation")
class FirstUseReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ascentiq-report-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        shutil.copytree(ROOT / "dashboard" / "templates", self.root / "dashboard" / "templates")
        rebuild(self.root)
        self.snapshot = build_snapshot(self.root, date(2026, 10, 3))

    def compile(self, snapshot, job_id):
        metadata = publish_report(snapshot, job_id, self.runtime, self.root)
        archive = self.runtime / "reports" / job_id
        pdf = PdfReader(archive / "report.pdf")
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        html = (archive / "dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(metadata["pdf_scope"], "training")
        self.assertEqual(json.loads((self.runtime / "latest.json").read_text())["id"], job_id)
        return pdf, text, html

    def test_empty_installation_compiles_without_inventing_load_or_author(self):
        self.assertEqual(self.snapshot["activities"], [])
        self.assertEqual(self.snapshot["strength"], [])
        self.assertEqual(self.snapshot["performance"]["summary"], {})
        self.assertEqual(self.snapshot["performance"]["series"], [])
        self.assertIsNone(self.snapshot["athlete"]["name"])
        self.assertIsNone(self.snapshot["freshness"]["activities"])
        pdf, text, html = self.compile(self.snapshot, "synthetic-empty")
        self.assertFalse(pdf.metadata.get("/Author"))
        for output in (text, html):
            self.assertIn("Sem dado", output)
            self.assertIn("Sem atividades registradas", output)
            self.assertIn("Sem corridas registradas", output)
            self.assertIn("Sem sessões de força registradas", output)
            self.assertNotIn("0 km", output)
        self.assertNotIn("<img ", html)
        self.assertNotIn("<td>0</td>", html)
        self.assertIn("Baixar PDF", html)

    def test_populated_report_compiles_and_pdf_excludes_private_fields(self):
        snapshot = copy.deepcopy(self.snapshot)
        markers = {key: f"PRIVATE_{key.upper()}_SYNTHETIC" for key in
                   ("body", "medical", "nutrition", "physiology", "sleep", "recovery", "health_goal", "goals", "credentials")}
        snapshot["body"]["current"]["weight_kg"] = markers["body"]
        snapshot["medical"]["status"]["cardiovascular_summary"] = markers["medical"]
        snapshot["nutrition"] = {"secret": markers["nutrition"]}
        snapshot["physiology"] = [{"secret": markers["physiology"]}]
        snapshot["sleep"]["secret"] = markers["sleep"]
        snapshot["performance"]["summary"] = {"fitness": 1, "fatigue": 2, "form": -1,
                                                  "recovery": {"secret": markers["recovery"]}}
        snapshot["athlete"].update(name="Synthetic Athlete", current_goal=markers["health_goal"])
        snapshot["goals"]["health"] = markers["goals"]
        snapshot["credentials"] = {"secret": markers["credentials"]}
        snapshot["activities"] = [{"id": "synthetic-activity", "date": "2026-10-03", "name": "Synthetic Run",
                                    "kind": "running", "distance_km": 2, "elapsed_time": "00:12:00",
                                    "avg_hr": 120, "elevation_gain_m": 3}]
        snapshot["freshness"]["activities"] = "2026-10-03"
        snapshot["performance"]["series"] = [{"date": "2026-10-03", "fitness": 1, "fatigue": 2,
                                               "form": -1, "daily_load": 3}]
        snapshot["week"].update(activity_count=1, running_km=2, running_elevation_m=3)
        allowed = json.dumps(training_snapshot(snapshot))
        pdf, text, html = self.compile(snapshot, "synthetic-populated")
        self.assertEqual(pdf.metadata.get("/Author"), "Synthetic Athlete")
        self.assertIn("Synthetic Run", text)
        for marker in markers.values():
            self.assertNotIn(marker, allowed)
            self.assertNotIn(marker, text + str(pdf.metadata))
        # The authenticated HTML retains health context; only the PDF has the training allowlist.
        self.assertIn(markers["body"], html)
        self.assertIn(markers["medical"], html)
        self.assertIn("<img ", html)


if __name__ == "__main__":
    unittest.main()
