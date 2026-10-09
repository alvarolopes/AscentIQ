import { expect, test } from '@playwright/test';

test('the Next API adapter preserves cookies, Host, Origin and CSRF protection', async ({
  request,
}) => {
  const url = 'http://127.0.0.1:18790';
  const missing = await request.post(`${url}/api/auth/login`, {
    data: { username: 'synthetic', password: 'synthetic-password' },
  });
  expect(missing.status()).toBe(403);
  const hostile = await request.post(`${url}/api/auth/login`, {
    data: { username: 'synthetic', password: 'synthetic-password' },
    headers: { 'X-AscentIQ-Request': '1', Origin: 'https://untrusted.invalid' },
  });
  expect(hostile.status()).toBe(403);
  const login = await request.post(`${url}/api/auth/login`, {
    data: { username: 'synthetic', password: 'synthetic-password' },
    headers: { 'X-AscentIQ-Request': '1', Origin: url },
  });
  expect(login.ok()).toBeTruthy();
  expect(login.headers()['set-cookie']).toContain('HttpOnly');
  const session = await request.get(`${url}/api/auth/session`);
  expect(session.ok()).toBeTruthy();
  expect(session.headers()['cache-control']).toContain('no-store');
});
