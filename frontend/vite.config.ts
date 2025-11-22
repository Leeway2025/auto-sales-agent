import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  },
  optimizeDeps: {
    include: ['microsoft-cognitiveservices-speech-sdk']
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          speech: ['microsoft-cognitiveservices-speech-sdk']
        }
      }
    }
  }
})
