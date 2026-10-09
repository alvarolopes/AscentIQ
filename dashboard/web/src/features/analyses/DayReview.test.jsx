// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DayReview from './DayReview';
import { personalApi } from '@/lib/personalApi';

vi.mock('@/lib/personalApi', async (importOriginal) => ({
  ...(await importOriginal()),
  personalApi: vi.fn(),
}));
const response = (text = 'Relatório salvo', stale = false) => ({
  configured: true,
  stale,
  report: {
    text,
    created_at: '2026-10-08T15:00:00-03:00',
    model: 'test-local',
    prompt: 'Contexto sintético',
    context: { user_report: 'Relato salvo' },
  },
  context: {},
  references: [],
});
beforeEach(() => {
  personalApi.mockReset();
  personalApi.mockResolvedValue(response());
});
afterEach(cleanup);

describe('daily review migration behavior', () => {
  it('keeps the report and unsaved notes while refreshed data marks the analysis stale', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const state = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <DayReview day="2026-10-08" revision={1} onStateChange={state} />
      </QueryClientProvider>,
    );
    await screen.findByText('Relatório salvo');
    fireEvent.change(screen.getByLabelText('Como foi seu dia? (opcional)'), {
      target: { value: 'Senti pouca energia na corrida' },
    });
    client.setQueryData(['day-review', '2026-10-08'], response('Relatório salvo', true));
    await screen.findByText('Registros alterados');
    expect(screen.getByText('Relatório salvo')).toBeTruthy();
    expect(screen.getByLabelText('Como foi seu dia? (opcional)').value).toBe(
      'Senti pouca energia na corrida',
    );
    await waitFor(() => expect(state).toHaveBeenLastCalledWith({ busy: false, dirty: true }));
  });

  it('does not display the previous date report or draft when the selected date changes', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    let finishNext;
    const next = new Promise((resolve) => {
      finishNext = resolve;
    });
    personalApi.mockImplementation((path) =>
      path === 'day-review/2026-10-09' ? next : Promise.resolve(response()),
    );
    const view = render(
      <QueryClientProvider client={client}>
        <DayReview day="2026-10-08" revision={1} />
      </QueryClientProvider>,
    );
    await screen.findByText('Relatório salvo');
    fireEvent.change(screen.getByLabelText('Como foi seu dia? (opcional)'), {
      target: { value: 'Rascunho do dia anterior' },
    });
    view.rerender(
      <QueryClientProvider client={client}>
        <DayReview day="2026-10-09" revision={1} />
      </QueryClientProvider>,
    );
    expect(screen.queryByText('Relatório salvo')).toBeNull();
    expect(screen.getByLabelText('Como foi seu dia? (opcional)').value).toBe('');
    finishNext(response('Relatório novo'));
    await screen.findByText('Relatório novo');
  });
});
