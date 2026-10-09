import unittest

from dashboard.frequency import frequency


class FrequencyTests(unittest.TestCase):
    def test_counts_records_without_linked_duplicates_and_preserves_pending(self):
        day='2026-10-06'
        snapshot={'sleep':{'daily':[{'date':day,'duration_minutes':480}]},
                  'strength':[{'date':day,'garmin_activity_ids':['linked']}],
                  'activities':[{'date':day,'id':'linked','kind':'strength'},
                                {'date':day,'id':'run','kind':'running','distance_km':10}]}
        food={day:{'entries':[{'analysis':{'items':[{'kcal':1600}]}},{'analysis':None}]}}
        rows=frequency(snapshot,food,2026)['days']
        row=next(r for r in rows if r['date']==day)
        self.assertEqual(row['count'],4)
        self.assertEqual(row['strength_count'],1)
        self.assertEqual(row['running_km'],10)
        self.assertEqual(row['sleep_minutes'],480)
        self.assertEqual(row['kcal'],1600)
        self.assertEqual(row['pending_count'],1)
        self.assertEqual(rows[0]['count'],0)

    def test_repeated_meals_and_sessions_count_each_category_once(self):
        day='2026-10-06'
        food={day:{'entries':[{'analysis':{'items':[{'kcal':400}]}} for _ in range(4)]}}
        row=next(r for r in frequency({},food,2026)['days'] if r['date']==day)
        self.assertEqual(row['count'],1)
        self.assertEqual(row['meal_count'],4)
        self.assertEqual(row['kcal'],1600)
        snapshot={'activities':[{'date':day,'id':str(i),'kind':'running','distance_km':5} for i in range(2)],
                  'strength':[{'date':day},{'date':day}]}
        row=next(r for r in frequency(snapshot,food,2026)['days'] if r['date']==day)
        self.assertEqual(row['count'],3)
        self.assertEqual(row['running_km'],10)
        self.assertEqual(row['strength_count'],2)

    def test_leap_year_and_unknown_distances_remain_unknown(self):
        rows=frequency({'activities':[{'date':'2024-02-29','kind':'running'}]}, {},2024)['days']
        self.assertEqual(len(rows),366)
        row=next(r for r in rows if r['date']=='2024-02-29')
        self.assertEqual(row['count'],1)
        self.assertIsNone(row['running_km'])
