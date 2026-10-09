import { expect, test } from '@playwright/test';

test('assistant keeps a conflict explanation and draft while refreshing context for retry', async ({
  page,
}) => {
  let fingerprint = 'synthetic-before-conflict';
  let attempts = 0;
  const contexts: string[] = [];
  await page.route('**/api/assistant/context?*', async (route) => {
    const response = await route.fetch();
    const context = await response.json();
    contexts.push(fingerprint);
    await route.fulfill({ response, json: { ...context, fingerprint } });
  });
  await page.route('**/api/assistant', async (route) => {
    attempts += 1;
    if (attempts === 1) {
      fingerprint = 'synthetic-after-conflict';
      await route.fulfill({
        status: 409,
        json: { detail: 'Os registros mudaram. Confira o contexto e tente novamente.' },
      });
    } else {
      await route.continue();
    }
  });
  await page.goto('/login');
  await page.getByLabel('Usuário', { exact: true }).fill('synthetic');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('button', { name: 'Assistente', exact: true }).click();
  const assistant = page.getByRole('region', { name: 'Assistente pessoal', exact: true });
  const question = assistant.getByLabel('Sua pergunta', { exact: true });
  const send = assistant.getByRole('button', { name: 'Perguntar à IA', exact: true });
  await question.fill('Como devo interpretar meu dia sintético?');
  await expect(send).toBeEnabled();
  await send.click();
  await expect.poll(() => contexts.includes('synthetic-after-conflict')).toBe(true);
  await expect(send).toBeEnabled();
  await expect(assistant.getByRole('alert')).toContainText('Os registros mudaram.');
  await expect(question).toHaveValue('Como devo interpretar meu dia sintético?');
  const retry = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/assistant') && response.request().method() === 'POST',
  );
  await send.click();
  const response = await retry;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON().fingerprint).toBe('synthetic-after-conflict');
  await expect(question).toHaveValue('');
  await expect(assistant.getByRole('alert')).toHaveCount(0);
});
