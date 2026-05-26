import { defineConfig } from 'vite';

export default defineConfig({
  base: '/static/',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: './index.html',
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
});
