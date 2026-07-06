import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: [
      'tests/robotsix_cost_monitor/web/static/*.test.js',
      'tests/web/*.test.js',
    ],
  },
});
