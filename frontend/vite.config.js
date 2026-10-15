import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // host lets a phone on the local network open the app for door simulator testing.
    host: true,
    // Tunnelled hostnames reach the dev server with their own Host header, which Vite blocks by default.
    // A leading dot covers every subdomain, so a new tunnel URL needs no config change.
    allowedHosts: [".loca.lt", ".ngrok-free.app", ".trycloudflare.com"],
    proxy: {
      // changeOrigin lets a phone on the local network reach Django through this proxy.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
})
