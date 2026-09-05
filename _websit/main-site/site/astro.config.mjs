import { defineConfig } from 'astro/config';

// 静态站点输出到 dist/，由 Nginx 托管
export default defineConfig({
  site: 'https://freetokens.info',
  output: 'static',
});
