/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
const backendHttpTarget = process.env.VITE_BACKEND_HTTP ?? 'http://127.0.0.1:8000'
const backendWsTarget = process.env.VITE_BACKEND_WS ?? 'ws://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    // Vitest 1.x runs test files in worker threads, one per core by default. On a 16-thread
    // machine that starved the heavy RigBuilder/RoomShell dialog files into timeouts; about
    // half the cores keeps a full run reliable. See docs/TESTING.md.
    poolOptions: {
      threads: { maxThreads: 8, minThreads: 1 },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backendHttpTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWsTarget,
        ws: true,
      },
    },
  },
})
