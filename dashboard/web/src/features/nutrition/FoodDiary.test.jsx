// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import FoodDiary from './FoodDiary';
import { personalApi } from '@/lib/personalApi';

vi.mock('@/lib/personalApi', async (importOriginal) => ({
  ...(await importOriginal()),
  personalApi: vi.fn(),
}));

const initialDiary = () => ({
  entries: [],
  revision: 1,
  completeness: 'empty',
  pending_count: 0,
  totals: {},
  targets: { kcal: 2400, protein_g: 180 },
  configured: true,
  local: true,
  model: 'test-local',
});
const storedMeal = (id, analysis = null) => ({
  id,
  meal: 'Lanche',
  text: 'Iogurte com banana',
  analysis,
  source: 'ai_estimated',
});
function renderDiary() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FoodDiary initialDay="2026-10-08" />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  personalApi.mockReset();
  personalApi.mockImplementation(async (path) => {
    if (path === 'food/2026-10-08') return initialDiary();
    if (path === 'food-library') return { recipes: [] };
    if (path === 'nutrition-targets/2026-10-08') return { kcal: 2400, protein_g: 180 };
    if (path === 'ai/configuration') return { configured: true, local: true, model: 'test-local' };
    throw new Error(`Unexpected endpoint ${path}`);
  });
});
afterEach(cleanup);

describe('nutrition migration behavior', () => {
  it('guards duplicate saves while the automatic estimate is running', async () => {
    let finish;
    const saved = new Promise((resolve) => {
      finish = resolve;
    });
    const read = personalApi.getMockImplementation();
    personalApi.mockImplementation((path, body) =>
      path.endsWith('/save') ? saved : read(path, body),
    );
    renderDiary();
    fireEvent.click(await screen.findByRole('button', { name: 'Adicionar refeição' }));
    fireEvent.change(screen.getByLabelText('O que você comeu?'), {
      target: { value: 'Iogurte com banana' },
    });
    const save = screen.getByRole('button', { name: 'Salvar refeição' });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() =>
      expect(personalApi.mock.calls.filter(([path]) => path.endsWith('/save'))).toHaveLength(1),
    );
    const body = personalApi.mock.calls.find(([path]) => path.endsWith('/save'))[1];
    expect(body).toMatchObject({ estimate_on_save: true, revision: 1, text: 'Iogurte com banana' });
    expect(body.id).toBeTruthy();
    expect(body.save_token).toBeTruthy();
    finish({
      ...initialDiary(),
      revision: 2,
      entries: [
        storedMeal(body.id, {
          items: [{ name: 'Iogurte com banana', kcal: 220, protein_g: 12, carbs_g: 30, fat_g: 5 }],
        }),
      ],
      analysis_status: 'estimated',
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(1);
  });

  it('keeps a saved pending meal and reuses its identity after an AI failure', async () => {
    const read = personalApi.getMockImplementation();
    let attempts = 0;
    personalApi.mockImplementation(async (path, body) => {
      if (!path.endsWith('/save')) return read(path, body);
      attempts++;
      const analysis =
        attempts === 1
          ? null
          : {
              items: [
                { name: 'Iogurte com banana', kcal: 220, protein_g: 12, carbs_g: 30, fat_g: 5 },
              ],
            };
      return {
        ...initialDiary(),
        revision: attempts + 1,
        entries: [storedMeal(body.id, analysis)],
        analysis_status: attempts === 1 ? 'pending' : 'estimated',
        analysis_error: attempts === 1 ? 'Modelo indisponível.' : null,
      };
    });
    renderDiary();
    fireEvent.click(await screen.findByRole('button', { name: 'Adicionar refeição' }));
    fireEvent.change(screen.getByLabelText('O que você comeu?'), {
      target: { value: 'Iogurte com banana' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar refeição' }));
    await screen.findByText(/A IA não concluiu a estimativa/);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByLabelText('O que você comeu?').value).toBe('Iogurte com banana');
    fireEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const writes = personalApi.mock.calls.filter(([path]) => path.endsWith('/save'));
    expect(writes).toHaveLength(2);
    expect(writes[1][1].id).toBe(writes[0][1].id);
    expect(writes[1][1].revision).toBe(2);
    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(1);
  });

  it('asks before discarding a meal draft', async () => {
    renderDiary();
    fireEvent.click(await screen.findByRole('button', { name: 'Adicionar refeição' }));
    fireEvent.change(screen.getByLabelText('O que você comeu?'), {
      target: { value: 'Iogurte com banana' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Fechar Adicionar refeição' }));
    expect(await screen.findByRole('alertdialog')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Continuar editando' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(screen.getByLabelText('O que você comeu?').value).toBe('Iogurte com banana');
    expect(personalApi.mock.calls.filter(([path]) => path.endsWith('/save'))).toHaveLength(0);
  });
});
