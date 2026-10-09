import { describe, expect, it } from 'vitest';
import { safeReturnTo } from './return-to';

const origin = 'https://ascentiq.test';

describe('safeReturnTo', () => {
  it('preserves internal paths, query parameters and fragments after normalization', () => {
    expect(safeReturnTo('/nutrition?day=2026-10-08#meals', origin)).toBe(
      '/nutrition?day=2026-10-08#meals',
    );
    expect(safeReturnTo('/workouts/../sleep', origin)).toBe('/sleep');
  });

  it.each([
    '//untrusted.invalid/path',
    '/\\untrusted.invalid/path',
    '/\n/untrusted.invalid/path',
    'https://untrusted.invalid/path',
    'javascript:alert(1)',
  ])('rejects an external or protocol destination: %s', (value) => {
    expect(safeReturnTo(value, origin)).toBe('/');
  });
});
