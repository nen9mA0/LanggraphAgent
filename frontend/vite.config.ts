import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))
const workspaceRoot = fileURLToPath(new URL('..', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  root: frontendRoot,
  envDir: workspaceRoot,
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (
            id.includes('node_modules/react/') ||
            id.includes('node_modules\\react\\') ||
            id.includes('node_modules/react-dom/') ||
            id.includes('node_modules\\react-dom\\') ||
            id.includes('scheduler')
          ) {
            return 'react-core'
          }

          if (id.includes('monaco-editor') || id.includes('@monaco-editor')) {
            return 'monaco'
          }

          if (id.includes('reactflow')) {
            return 'reactflow'
          }

          if (id.includes('@mui') || id.includes('@emotion')) {
            return 'mui'
          }

          if (id.includes('framer-motion')) {
            return 'motion'
          }

          if (
            id.includes('react-hot-toast') ||
            id.includes('react-toastify')
          ) {
            return 'toast'
          }

          if (
            id.includes('react-dropzone') ||
            id.includes('file-selector') ||
            id.includes('attr-accept')
          ) {
            return 'dropzone'
          }

          if (id.includes('react-icons') || id.includes('@heroicons')) {
            return 'icons'
          }

          if (id.includes('axios') || id.includes('follow-redirects')) {
            return 'network'
          }

          if (id.includes('zustand')) {
            return 'state'
          }

          if (
            id.includes('react-syntax-highlighter') ||
            id.includes('refractor') ||
            id.includes('prismjs')
          ) {
            return 'syntax-highlighter'
          }

          if (
            id.includes('react-router') ||
            id.includes('@tanstack/react-query')
          ) {
            return 'app-vendor'
          }

          return 'vendor'
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
  },
  preview: {
    host: '0.0.0.0',
  },
})
