import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/web/**/*.test.js', 'tests/robotsix_cost_monitor/web/static/*.test.js'],
  },
});
