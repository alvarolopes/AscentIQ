import { describe, expect, it } from 'vitest';
import { sleepDays, sleepAverage, sleepDuration } from './sleepView';

describe('sleep calendar semantics', () => {
  it('preserves missing dates and does not include missing duration in the mean', () => {
    const rows = sleepDays(
      [
        { date: '2026-09-29', duration_minutes: 514 },
        { date: '2026-10-01', duration_minutes: 446 },
      ],
      '2026-09-29',
      '2026-10-01',
    );
    expect(rows).toHaveLength(3);
    expect(rows[1]).toMatchObject({ date: '2026-09-30', recorded: false, hours: null });
    expect(sleepAverage(rows, 'duration_minutes')).toEqual({ value: 480, count: 2 });
  });

  it('counts a real zero score and preserves score-only nights', () => {
    const rows = sleepDays(
      [
        { date: '2026-10-01', score: 0 },
        { date: '2026-10-02', score: 80 },
      ],
      '2026-10-01',
      '2026-10-03',
    );
    expect(rows[0]).toMatchObject({ recorded: true, hours: null, score: 0 });
    expect(sleepAverage(rows, 'score')).toEqual({ value: 40, count: 2 });
    expect(sleepAverage(rows, 'duration_minutes')).toEqual({ value: null, count: 0 });
    expect(sleepDuration(464)).toBe('7h44');
    expect(sleepDuration(null)).toBe('Sem dado');
  });

  it('supports the entire requested calendar and rejects reversed or empty periods', () => {
    expect(sleepDays([], '2024-02-28', '2024-03-01').map((row) => row.date)).toEqual([
      '2024-02-28',
      '2024-02-29',
      '2024-03-01',
    ]);
    expect(sleepDays([], '2026-10-02', '2026-10-01')).toEqual([]);
    expect(sleepDays([], '', '2026-10-01')).toEqual([]);
  });
});
