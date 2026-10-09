import { defineConfig, devices } from '@playwright/test';

const externalPreview = process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  timeout: 45000,
  expect: { timeout: 10000 },
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: externalPreview || 'http://127.0.0.1:18789',
    timezoneId: 'America/Sao_Paulo',
    locale: 'pt-BR',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } },
    },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'], defaultBrowserType: 'chromium' } },
  ],
  webServer: externalPreview
    ? undefined
    : [
        {
          command: 'node tests/e2e/fixtures/synthetic-server.mjs',
          url: 'http://127.0.0.1:18788/api/health',
          reuseExistingServer: false,
          timeout: 15000,
        },
        {
          command: 'node scripts/start-production.mjs',
          url: 'http://127.0.0.1:18790/healthz',
          reuseExistingServer: false,
          timeout: 60000,
          env: { BACKEND_INTERNAL_URL: 'http://127.0.0.1:18788', NEXT_TELEMETRY_DISABLED: '1', PORT:'18790', HOSTNAME:'127.0.0.1' },
        },
      ],
});
