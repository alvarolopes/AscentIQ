import tempfile
import unittest
from datetime import date
from pathlib import Path
from dashboard.nutrition import FoodDiary, validate


class FoodTests(unittest.TestCase):
    def test_roundtrip_totals_retry_and_remove(self):
        with tempfile.TemporaryDirectory() as folder:
            diary = FoodDiary(Path(folder))
            day = date(2026, 10, 2)
            analysis = validate({'items': [{'name': 'Banana', 'kcal': 100,
                'protein_g': 1, 'carbs_g': 25, 'fat_g': 0}]})
            entry = {'id': 'one', 'analysis': analysis}
            diary.change(day, entry=entry)
            diary.change(day, entry=entry)
            self.assertEqual(FoodDiary(Path(folder)).read(day)['totals']['kcal'], 100)
            self.assertEqual(diary.read(date(2026, 10, 1))['entries'], [])
            self.assertEqual(diary.change(day, remove='one')['totals']['kcal'], 0)

    def test_invalid_estimates(self):
        for value in (-1, float('nan'), float('inf'), '100', True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate({'items': [{'name': 'Alimento', 'kcal': value,
                    'protein_g': 0, 'carbs_g': 0, 'fat_g': 0}]})
        with self.assertRaises(ValueError):
            validate({'items': []})
