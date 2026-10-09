import { expect, test } from '@playwright/test';

test('a new browser activates the public offline shell without caching personal data', async ({
  page,
  context,
}) => {
  await page.goto('/login');
  expect(
    await page.evaluate(() =>
      navigator.serviceWorker.getRegistrations().then((rows) => rows.length),
    ),
  ).toBe(0);
  await page.getByLabel('Usuário', { exact: true }).fill('synthetic');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? ''))
    .toContain('/sw.js');
  const cachedPaths = await page.evaluate(async () => {
    const keys = await caches.keys();
    const paths = await Promise.all(
      keys.map(async (key) =>
        (await (await caches.open(key)).keys()).map((request) => new URL(request.url).pathname),
      ),
    );
    return paths.flat().sort();
  });
  expect(cachedPaths).toEqual([
    '/icon-180.png',
    '/icon-192.png',
    '/icon-512.png',
    '/icon-maskable.png',
    '/icon.svg',
    '/offline.html',
  ]);
  await context.setOffline(true);
  try {
    await page.goto('/nutrition');
    await expect(
      page.getByRole('heading', { name: 'Sem conexão com seu painel', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText('Esta tela não armazena dados pessoais.', { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Nutrition', exact: true })).toHaveCount(0);
  } finally {
    await context.setOffline(false);
  }
});
