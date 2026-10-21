import { defineConfig } from 'vite';
export default defineConfig({
  base: '/ui/',
  build: { sourcemap: false, rollupOptions: {output: {
    entryFileNames: 'mission.js', assetFileNames: 'mission.[ext]',
  }}},
});
