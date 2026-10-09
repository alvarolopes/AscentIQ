// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Frequency from './Frequency';
import { personalApi } from '@/lib/personalApi';

vi.mock('@/lib/personalApi', async (importOriginal) => ({
  ...(await importOriginal()),
  personalApi: vi.fn(),
}));
const day = {
  date: '2026-10-08',
  count: 1,
  meal_count: 4,
  kcal: 1600,
  pending_count: 0,
  running_count: 0,
  strength_count: 0,
  sleep_minutes: null,
};
beforeEach(() => {
  personalApi.mockReset();
  personalApi.mockResolvedValue({ year: 2026, days: [day] });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('frequency migration behavior', () => {
  it('uses the category count and shows only labels for present records on click', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Frequency revision={1} initialYear={2026} />
      </QueryClientProvider>,
    );
    const cell = await screen.findByRole('button', {
      name: '08/10/2026: 1 categorias registradas',
    });
    expect(cell.className).toContain('frequency-level-1');
    fireEvent.click(cell);
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip.textContent).toContain('Alimentação');
    expect(tooltip.textContent).toContain('1.600 kcal');
    expect(tooltip.textContent).not.toContain('Sono');
    expect(tooltip.textContent).not.toContain('Corrida');
    expect(tooltip.textContent).not.toContain('Força');
    client.setQueryData(['frequency', 2026], { year: 2026, days: [{ ...day, kcal: 1700 }] });
    await screen.findByText('1.700 kcal');
    expect(screen.getByRole('tooltip')).toBeTruthy();
  });
});
