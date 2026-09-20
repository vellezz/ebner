import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://ebner.gripe',
  output: 'static',
  build: { format: 'directory' },
});
