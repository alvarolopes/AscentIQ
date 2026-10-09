import { expect, test, type Page } from '@playwright/test';

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Usuário', { exact: true }).fill('synthetic');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: /Acessar dashboard|Entrar|Acessar/ }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
}

async function openTrainingAnalysis(page: Page) {
  let navigation = page
    .getByRole('navigation', { name: 'Áreas do painel' })
    .filter({ visible: true });
  if ((await navigation.count()) === 0) {
    await page.getByRole('button', { name: 'Abrir menu principal', exact: true }).click();
    navigation = page
      .getByRole('navigation', { name: 'Áreas do painel' })
      .filter({ visible: true });
  }
  await navigation.getByText('Workouts', { exact: true }).click();
  await expect(page).toHaveURL(/\/workouts$/);
  await page.getByRole('button', { name: 'Analisar treinos do dia', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Análise dos treinos', exact: true });
  await expect(dialog.getByText('2 sessões', { exact: true })).toBeVisible();
  return dialog;
}

test('training analysis generates, imports and persists its report', async ({ page }) => {
  await login(page);
  let dialog = await openTrainingAnalysis(page);
  const day = await dialog.getByLabel('Dia do treino', { exact: true }).inputValue();
  const generated = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/daily-analysis/${day}`) &&
      response.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Gerar análise com IA', exact: true }).click();
  const generation = await generated;
  expect(generation.ok()).toBeTruthy();
  expect(generation.request().postDataJSON().fingerprint).toMatch(/^[a-f0-9]{64}$/);
  expect(generation.request().postDataJSON()).not.toHaveProperty('text');
  await expect(
    dialog.getByText('O treino combinou endurance e força. Priorize recuperação.', { exact: true }),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'Fechar Análise dos treinos', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Analisar treinos do dia', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'Análise dos treinos', exact: true });
  await expect(
    dialog.getByText('O treino combinou endurance e força. Priorize recuperação.', { exact: true }),
  ).toBeVisible();
  const stored = await (await page.request.get(`/api/daily-analysis/${day}`)).json();
  expect(stored.report.source).toBe('ollama');
  expect(stored.context.session_count).toBe(2);
  await dialog.getByText('Importar resposta de uma IA', { exact: true }).click();
  const text = 'Resposta externa sintética: mantenha recuperação adequada após corrida e força.';
  await dialog.getByLabel('Resposta da IA', { exact: true }).fill(text);
  const imported = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/daily-analysis/${day}`) &&
      response.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Salvar e exibir relatório', exact: true }).click();
  const importResponse = await imported;
  expect(importResponse.ok()).toBeTruthy();
  expect(importResponse.request().postDataJSON().text).toBe(text);
  await expect(dialog.getByText(text, { exact: true })).toBeVisible();
  const saved = await (await page.request.get(`/api/daily-analysis/${day}`)).json();
  expect(saved.report).toMatchObject({ source: 'imported', model: 'Resposta importada', text });
  expect(saved.report.fingerprint).toBe(stored.fingerprint);
});

test('a date without training shows zero sessions and disables generation and import', async ({
  page,
}) => {
  await login(page);
  const dialog = await openTrainingAnalysis(page);
  const selected = await dialog.getByLabel('Dia do treino', { exact: true }).inputValue();
  const date = new Date(selected + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() - 10);
  const emptyDay = date.toISOString().slice(0, 10);
  const context = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/daily-analysis/${emptyDay}`) &&
      response.request().method() === 'GET',
  );
  await dialog.getByLabel('Dia do treino', { exact: true }).fill(emptyDay);
  expect((await (await context).json()).context.session_count).toBe(0);
  await expect(dialog.getByText('0 sessões', { exact: true })).toBeVisible();
  await expect(
    dialog.getByText('Não há registros nessa data. Escolha outro dia ou atualize seus treinos.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Gerar análise com IA', exact: true }),
  ).toBeDisabled();
  await expect(dialog.getByRole('button', { name: 'Copiar prompt', exact: true })).toBeDisabled();
  await dialog.getByText('Importar resposta de uma IA', { exact: true }).click();
  await dialog
    .getByLabel('Resposta da IA', { exact: true })
    .fill('Resposta sintética para data sem nenhuma atividade.');
  await expect(
    dialog.getByRole('button', { name: 'Salvar e exibir relatório', exact: true }),
  ).toBeDisabled();
});

test('check-in saves its day context and the goals modal exposes the current plan', async ({
  page,
}) => {
  await login(page);
  await page.getByRole('button', { name: 'Registrar check-in', exact: true }).first().click();
  let dialog = page.getByRole('dialog', { name: /^Check-in ·/ });
  await dialog
    .getByLabel('Como você está hoje?', { exact: true })
    .fill('Contexto sintético: disposição boa e recuperação adequada.');
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/personal/checkins') && response.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Salvar check-in', exact: true }).click();
  expect((await saved).ok()).toBeTruthy();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Editar check-in', exact: true }).first().click();
  dialog = page.getByRole('dialog', { name: /^Check-in ·/ });
  await expect(dialog.getByLabel('Como você está hoje?', { exact: true })).toHaveValue(
    'Contexto sintético: disposição boa e recuperação adequada.',
  );
  await dialog.getByRole('button', { name: /^Fechar Check-in/ }).click();
  await page.getByRole('button', { name: 'Objetivos', exact: true }).click();
  const goals = page.getByRole('dialog', { name: 'Objetivos e plano', exact: true });
  await expect(goals.getByText('Plano vigente', { exact: true })).toBeVisible();
  await expect(
    goals.getByRole('heading', { name: 'Reduzir gordura preservando treino', exact: true }),
  ).toBeVisible();
});
