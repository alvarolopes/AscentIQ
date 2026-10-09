import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('active pages have no serious accessibility errors, hydration errors or page overflow', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (
      message.type() === 'error' &&
      /hydration|content.security.policy|violates.*policy/i.test(message.text())
    )
      errors.push(message.text());
  });
  await page.goto('/login');
  await page.getByLabel('Usuário', { exact: true }).fill('synthetic');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  for (const [url, title] of [
    ['/', 'Dashboard'],
    ['/nutrition', 'Nutrition'],
    ['/sleep', 'Sleep'],
    ['/workouts', 'Carga, adaptação e equilíbrio'],
  ] as const) {
    await page.goto(url);
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    const result = await new AxeBuilder({ page }).analyze();
    expect(
      result.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious'),
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(1);
  }
  expect(errors).toEqual([]);
});
