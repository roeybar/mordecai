import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'report/html', open: 'never' }]],
  use: {
    baseURL: process.env.BASE_URL || 'http://web:8080',
  },
});
