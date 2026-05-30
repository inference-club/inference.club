// https://nuxt.com/docs/api/configuration/nuxt-config

import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  runtimeConfig: {
    // Server-only base for SSR data fetches (NUXT_API_BASE_INTERNAL). The
    // browser uses public.apiBase; but during SSR inside a container that
    // browser-facing host (e.g. localhost:8101 in dev) isn't reachable, so SSR
    // must hit the backend by its internal address. Empty → fall back to
    // public.apiBase (correct for prod, where the public API host resolves).
    apiBaseInternal: '',
    public: {
      apiBase: 'http://localhost:8001'
    }
  },
  vite: {
    plugins: [
      tailwindcss(),
    ],
  },
  modules: [
    '@nuxt/content',
    '@nuxt/eslint',
    '@nuxt/fonts',
    '@nuxt/icon',
    '@nuxt/image',
    '@nuxt/scripts',
    '@nuxt/test-utils',
    '@pinia/nuxt',
    '@tresjs/nuxt',
    'shadcn-nuxt',
  ],
  components: {
    dirs: ['~/components', '~/components/ui']
  },
  shadcn: {
    /**
     * Prefix for all the imported component
     */
    prefix: '',
    /**
     * Directory that the component lives in.
     * @default "./components/ui"
     */
    componentDir: './components/ui'
  },
  css: [
    '@/assets/css/main.css'
  ],
})