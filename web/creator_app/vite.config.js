import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { creatorBackendPlugin } from './server/creatorBackendPlugin.js';

export default defineConfig({
  plugins: [creatorBackendPlugin(), react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 5174,
  },
});
