import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base relativo: la app se sirve desde /gemelo-digital-sag/ en GitHub Pages
// (repo de proyecto, no de usuario), pero './' evita hardcodear el nombre
// del repo y funciona igual en local (npm run dev) y en Pages.
export default defineConfig({
  plugins: [react()],
  base: './',
})
