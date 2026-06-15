// https://nuxt.com/docs/api/configuration/nuxt-config

import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  // The compose frontend bind-mounts this directory (/app) and runs its own
  // `nuxt dev`, so a bare-metal `yarn dev` on the host shares .nuxt with the
  // container — each writes absolute paths the other can't resolve and they
  // corrupt each other (the recurring "/app/... not found" / missing-entry-
  // script breakage). Run host-side dev with NUXT_LOCAL_BUILD_DIR=.nuxt-local
  // to keep the two build dirs apart.
  buildDir: process.env.NUXT_LOCAL_BUILD_DIR || undefined,
  app: {
    head: {
      title: 'inference.club',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'alternate icon', href: '/favicon.ico' },
      ],
    },
  },
  scripts: {
    registry: {
      // Google Analytics 4 (gtag.js), loaded site-wide by @nuxt/scripts. The
      // measurement ID is a public client-side token; default to the prod
      // property but allow an env override (NUXT_PUBLIC_GTAG_ID) per-environment.
      googleAnalytics: {
        id: process.env.NUXT_PUBLIC_GTAG_ID || 'G-SJR3D8KS94',
      },
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
    server: {
      // In the compose dev container Nuxt listens on :3000 but the browser
      // loads the app from the host-published :3100. By default Vite tells the
      // HMR client to connect on the *server's* port (3000), which isn't
      // published — so the browser's HMR WebSocket fails, retries in a tight
      // loop (console flooded with ws errors), and Vite falls back to full
      // page reloads: the app feels sluggish and laggy. Point the HMR client
      // at the published port instead. Env-gated so bare-metal `yarn dev`
      // (page + server on the same port) is left on Vite's correct default.
      hmr: process.env.NUXT_VITE_HMR_CLIENT_PORT
        ? { clientPort: Number(process.env.NUXT_VITE_HMR_CLIENT_PORT) }
        : undefined,
    },
    optimizeDeps: {
      // three example modules imported by the cluster scene + jack logo —
      // pre-bundle them so dev doesn't force-reload mid-navigation when the
      // optimizer discovers them at runtime.
      include: [
        'three/examples/jsm/geometries/RoundedBoxGeometry.js',
        'three/examples/jsm/environments/RoomEnvironment.js',
        'three/examples/jsm/loaders/OBJLoader.js',
        'three/examples/jsm/utils/BufferGeometryUtils.js',
      ],
    },
  },
  content: {
    build: {
      markdown: {
        highlight: {
          // Dual Shiki themes: MDC emits both palettes as CSS variables
          // (--shiki-default / --shiki-dark) and switches them on `html.dark`;
          // main.css keeps the surrounding pre chrome in sync.
          theme: { default: 'github-light', dark: 'github-dark' },
          // Every fence language used under content/ — a language missing
          // from this list silently renders as plain, unhighlighted text.
          langs: [
            'bash', 'json', 'jsonc', 'python', 'go', 'http', 'yaml',
            'js', 'ts', 'html', 'vue', 'scss', 'mdc',
          ],
        },
      },
    },
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
    // Absolute site URL — required so useLocaleHead() can emit valid (absolute)
    // hreflang/canonical SEO links. Static prod domain regardless of env.
    baseUrl: 'https://inference.club',
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
    // ~/components/content holds MDC components used inside markdown (blog,
    // docs). Nuxt Content only renders globally-registered components, so
    // that dir must opt into global.
    dirs: [
      { path: '~/components/content', global: true },
      '~/components',
      '~/components/ui',
    ]
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