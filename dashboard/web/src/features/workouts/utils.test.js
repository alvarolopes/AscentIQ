import { describe, expect, it } from 'vitest';
import { daysBefore, weeklyRunning, weeklyStrength } from './utils';

describe('workout presentation aggregates', () => {
  it('uses actual running distances and Monday buckets across year boundaries', () => {
    expect(
      weeklyRunning([
        { date: '2026-12-27', distance_km: 8.94 },
        { date: '2026-12-28', distance_km: 12.6 },
        { date: '2027-01-03', distance_km: null },
        { date: '2027-01-04', distance_km: 5.25 },
      ]),
    ).toEqual([
      { date: '2026-12-21', km: 8.94 },
      { date: '2026-12-28', km: 12.6 },
      { date: '2027-01-04', km: 5.25 },
    ]);
    expect(daysBefore('2027-01-01', 1)).toBe('2026-12-31');
  });

  it('aggregates working load times repetitions without warmup, core or unweighted sets', () => {
    expect(
      weeklyStrength([
        {
          date: '2026-10-05',
          exercises: [
            {
              name: 'Agachamento',
              sets: [
                { set_type: 'warmup', weight_kg: 20, reps: 10 },
                { set_type: 'normal', weight_kg: 80, reps: 8 },
              ],
            },
            {
              name: 'Supino',
              sets: [
                { set_type: 'normal', weight_kg: 40, reps: 10 },
                { set_type: 'normal', weight_kg: 0, reps: 12 },
              ],
            },
            { name: 'Prancha', sets: [{ set_type: 'normal', weight_kg: 20, reps: 10 }] },
          ],
        },
        {
          date: '2026-10-08',
          exercises: [{ name: 'Remada', sets: [{ set_type: 'normal', weight_kg: 30, reps: 12 }] }],
        },
      ]),
    ).toEqual([{ date: '2026-10-05', legs: 640, upper: 760 }]);
  });
});
