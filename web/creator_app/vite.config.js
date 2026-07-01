import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const runtimeProxyTarget = process.env.CREATOR_APP_RUNTIME_PROXY_TARGET || 'http://127.0.0.1:8093';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/runtime-api': {
        target: runtimeProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/runtime-api/, ''),
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5174,
  },
});
