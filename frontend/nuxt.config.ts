// https://nuxt.com/docs/api/configuration/nuxt-config

import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  app: {
    head: {
      title: 'inference.club',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'alternate icon', href: '/favicon.ico' },
      ],
    },
  },
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
    '@nuxtjs/i18n',
    '@pinia/nuxt',
    '@tresjs/nuxt',
    'shadcn-nuxt',
  ],
  i18n: {
    // Locale message files live in i18n/locales/ (v9 restructureDir default is
    // `i18n`, so langDir is relative to it). Adding a language = one entry
    // here + one i18n/locales/<code>.json + one content/<code>/ folder.
    langDir: 'locales',
    defaultLocale: 'en',
    // English keeps clean URLs (/blog); every other locale is path-prefixed
    // (/fr/blog). No redirects for existing English links, best SEO.
    strategy: 'prefix_except_default',
    lazy: true,
    locales: [
      { code: 'en', language: 'en-US', name: 'English', file: 'en.json' },
      { code: 'zh', language: 'zh-CN', name: '中文', file: 'zh.json' },
      { code: 'ja', language: 'ja-JP', name: '日本語', file: 'ja.json' },
      { code: 'ru', language: 'ru-RU', name: 'Русский', file: 'ru.json' },
      { code: 'fr', language: 'fr-FR', name: 'Français', file: 'fr.json' },
      { code: 'ko', language: 'ko-KR', name: '한국어', file: 'ko.json' },
      { code: 'es', language: 'es-ES', name: 'Español', file: 'es.json' },
    ],
    // Fall back to English for any key missing in the active locale, so the
    // UI never shows a raw key while translations are filled in over time.
    bundle: { optimizeTranslationDirective: false },
    vueI18n: './i18n.config.ts',
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'i18n_locale',
      redirectOn: 'root',
      alwaysRedirect: false,
    },
  },
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