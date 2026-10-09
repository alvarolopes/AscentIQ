import { expect, test, type Page } from '@playwright/test';

type Snapshot = { as_of: string };

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Usuário', { exact: true }).fill('synthetic');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password');
  await page
    .getByRole('button', { name: /Acessar dashboard|Entrar|Acessar/, exact: false })
    .click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
}

async function navigate(page: Page, name: string) {
  let navigation = page
    .getByRole('navigation', { name: 'Áreas do painel' })
    .filter({ visible: true });
  if ((await navigation.count()) === 0) {
    await page.getByRole('button', { name: 'Abrir menu principal', exact: true }).click();
    navigation = page
      .getByRole('navigation', { name: 'Áreas do painel' })
      .filter({ visible: true });
  }
  await navigation.getByText(name, { exact: true }).click();
}

async function selectedDay(page: Page) {
  const response = await page.request.get('/api/dashboard');
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as Snapshot).as_of;
}

const dayLabel = (day: string) =>
  new Date(day + 'T12:00:00Z').toLocaleDateString('pt-BR', { timeZone: 'UTC' });
const offset = (day: string, days: number) => {
  const value = new Date(day + 'T12:00:00Z');
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
};

test('login, direct routes, workout data and same-origin protection', async ({ page }) => {
  const document = await page.goto('/workouts/running');
  await expect(page).toHaveURL(/\/login/);
  expect(document?.headers()['content-security-policy']).toContain("'nonce-");
  expect(document?.headers()['content-security-policy']).not.toContain('unsafe-eval');
  await login(page);
  await navigate(page, 'Workouts');
  await expect(page).toHaveURL(/\/workouts$/);
  await expect(
    page
      .getByRole('navigation', { name: 'Áreas de Workouts' })
      .getByRole('button', { name: 'Analisar treinos do dia' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Corrida', exact: true }).click();
  await expect(page).toHaveURL(/\/workouts\/running$/);
  await expect(page.getByRole('cell', { name: '8,94 km', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: '12,6 km', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Força', exact: true }).click();
  await expect(page.getByText('Força consolidada', { exact: true })).toBeVisible();
  await page.getByText('Força consolidada', { exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Agachamento', exact: true })).toBeVisible();
  const missingHeader = await page.request.post('/api/auth/login', {
    data: { username: 'synthetic', password: 'synthetic-password' },
  });
  expect(missingHeader.status()).toBe(403);
  const invalidOrigin = await page.request.post('/api/auth/login', {
    data: { username: 'synthetic', password: 'synthetic-password' },
    headers: { 'X-AscentIQ-Request': '1', Origin: 'https://untrusted.invalid' },
  });
  expect(invalidOrigin.status()).toBe(403);
});

test('meal save estimates automatically and protects an unsaved draft', async ({ page }) => {
  await login(page);
  await navigate(page, 'Nutrition');
  await page.getByRole('button', { name: 'Adicionar refeição', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'Adicionar refeição', exact: true });
  await editor
    .getByLabel('O que você comeu?', { exact: true })
    .fill('Arroz e frango sintéticos para validação.');
  await page.keyboard.press('Tab');
  await expect(editor.locator(':focus')).toHaveCount(1);
  await editor.getByRole('button', { name: 'Fechar Adicionar refeição', exact: true }).click();
  await expect(
    page.getByRole('alertdialog', { name: 'Descartar rascunho?', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Continuar editando', exact: true }).click();
  await expect(editor.getByLabel('O que você comeu?', { exact: true })).toHaveValue(
    'Arroz e frango sintéticos para validação.',
  );
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes('/api/food/') &&
      response.url().endsWith('/save') &&
      response.request().method() === 'POST',
  );
  await editor.getByRole('button', { name: 'Salvar refeição', exact: true }).click();
  const result = await saved;
  expect(result.ok()).toBeTruthy();
  expect(result.request().postDataJSON().estimate_on_save).toBe(true);
  await expect(editor).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Adicionar refeição', exact: true })).toBeFocused();
  await expect(
    page.getByText('Arroz e frango sintéticos para validação.', { exact: true }),
  ).toBeVisible();
  const day = await selectedDay(page),
    diary = await (await page.request.get(`/api/food/${day}`)).json();
  expect(diary.entries).toHaveLength(5);
  expect(diary.totals.kcal).toBe(2100);
});

test('a pending AI estimate survives failure and retry keeps the same meal', async ({ page }) => {
  await login(page);
  await navigate(page, 'Nutrition');
  await page.getByRole('button', { name: 'Adicionar refeição', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByLabel('O que você comeu?', { exact: true })
    .fill('Refeição sintética [pendente]');
  await page.getByRole('button', { name: 'Salvar refeição', exact: true }).click();
  await expect(
    page.getByRole('dialog').getByText(/IA sintética temporariamente indisponível/),
  ).toBeVisible();
  const day = await selectedDay(page),
    first = await (await page.request.get(`/api/food/${day}`)).json();
  expect(first.entries).toHaveLength(5);
  expect(first.pending_count).toBe(1);
  const pendingId = first.entries.at(-1).id;
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Salvar alterações', exact: true })
    .click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  const second = await (await page.request.get(`/api/food/${day}`)).json();
  expect(second.entries).toHaveLength(5);
  expect(second.entries.at(-1).id).toBe(pendingId);
  expect(second.pending_count).toBe(0);
});

test('sleep uses all selected days while the history stays paginated', async ({ page }) => {
  await login(page);
  const day = await selectedDay(page);
  await navigate(page, 'Sleep');
  await expect(page.getByRole('heading', { name: 'Sleep', exact: true })).toBeVisible();
  await expect(page.getByText('Sem registro', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Todo o histórico', exact: true }).click();
  const pagination = page.getByRole('navigation', {
    name: 'Paginação de registros de sono',
    exact: true,
  });
  await expect(pagination).toContainText('de 40');
  await expect(page.locator('table tbody tr')).toHaveCount(10);
  await expect(
    page
      .getByRole('row')
      .filter({ hasText: dayLabel(offset(day, 3)) })
      .getByRole('cell')
      .nth(2),
  ).toHaveText('0');
  await page
    .getByRole('button', { name: 'Próxima página de registros de sono', exact: true })
    .click();
  await expect(pagination).toContainText('11–20 de 40');
  await expect(page.getByText('40 dias no período', { exact: true })).toBeVisible();
});

test('heatmap counts categories and omits absent tooltip labels on touch', async ({ page }) => {
  await login(page);
  const day = await selectedDay(page),
    foodOnly = offset(day, 46);
  const today = page.locator(`[data-frequency-date="${day}"]`);
  await expect(today).toHaveAttribute('aria-label', /4 categorias/);
  await today.click();
  await expect(page.getByText('4 de 4 categorias', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator(`[data-frequency-date="${foodOnly}"]`).click();
  await expect(page.getByText('1 de 4 categorias', { exact: true })).toBeVisible();
  const tooltip = page
    .locator('[data-slot="popover-content"]')
    .filter({ hasText: dayLabel(foodOnly) });
  await expect(tooltip.getByText('Alimentação', { exact: true })).toBeVisible();
  await expect(tooltip.getByText('1.600 kcal', { exact: true })).toBeVisible();
  await expect(tooltip.getByText('Sono', { exact: true })).toHaveCount(0);
  await expect(tooltip.getByText('Corrida', { exact: true })).toHaveCount(0);
  await expect(tooltip.getByText('Força', { exact: true })).toHaveCount(0);
});

test('assistant remains nonmodal across navigation and medical context requires consent', async ({
  page,
}) => {
  await login(page);
  await page.getByRole('button', { name: 'Assistente', exact: true }).click();
  const assistant = page.getByRole('region', { name: 'Assistente pessoal', exact: true });
  await expect(assistant).toBeVisible();
  const question = assistant.getByLabel('Sua pergunta', { exact: true });
  await question.fill('Como foi meu dia sintético?');
  await assistant.getByRole('button', { name: 'Minimizar assistente', exact: true }).click();
  await navigate(page, 'Nutrition');
  await page.getByRole('button', { name: 'Abrir assistente', exact: true }).click();
  await expect(question).toHaveValue('Como foi meu dia sintético?');
  const firstAnswer = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/assistant') && response.request().method() === 'POST',
  );
  await assistant.getByRole('button', { name: 'Perguntar à IA', exact: true }).click();
  expect((await firstAnswer).request().postDataJSON().include_medical).toBe(false);
  await expect(
    assistant.getByText(
      'Você registrou alimentação, corrida e força. Continue acompanhando seu objetivo.',
      { exact: true },
    ),
  ).toBeVisible();
  await assistant.getByText('Contexto e opções', { exact: true }).click();
  const consent = assistant.getByRole('checkbox', {
    name: 'Incluir referências médicas e documentos registrados',
    exact: true,
  });
  await consent.check();
  const medical = await page.request.get('/api/assistant/context?include_medical=true');
  expect(JSON.stringify(await medical.json())).toContain('SYNTHETIC_MEDICAL_PRIVATE');
  await question.fill('Considere meus documentos autorizados.');
  const authorized = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/assistant') && response.request().method() === 'POST',
  );
  await assistant.getByRole('button', { name: 'Perguntar à IA', exact: true }).click();
  expect((await authorized).request().postDataJSON().include_medical).toBe(true);
  await consent.uncheck();
  const ordinary = await page.request.get('/api/assistant/context?include_medical=false');
  expect(JSON.stringify(await ordinary.json())).not.toContain('SYNTHETIC_MEDICAL_PRIVATE');
  await question.fill('Considere apenas alimentação e treino.');
  const revoked = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/assistant') && response.request().method() === 'POST',
  );
  await assistant.getByRole('button', { name: 'Perguntar à IA', exact: true }).click();
  const revokedResponse = await revoked;
  expect(revokedResponse.request().postDataJSON().include_medical).toBe(false);
  expect((await revokedResponse.json()).withheld_medical_turns).toBe(true);
});

test('logout removes access and returning in history does not expose the dashboard', async ({
  page,
}) => {
  await login(page);
  await navigate(page, 'Nutrition');
  await page.getByRole('button', { name: /Menu da conta de/ }).click();
  await page.getByRole('menuitem', { name: 'Sair', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  const session = await page.request.get('/api/auth/session');
  expect(session.status()).toBe(401);
  await page.goBack();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toHaveCount(0);
  await page.goto('/sleep');
  await expect(page).toHaveURL(/\/login/);
});
