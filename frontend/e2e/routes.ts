// Single source of truth for which pages the design suite covers. Every new
// page should get a row here — overflow guards and the screenshot sweep then
// cover it automatically on both viewports.
//
// `dynamic` routes contain a `:param` placeholder resolved at runtime from
// seeded data (see helpers.resolveDynamicRoutes). `auth` pages assume the
// designbot storageState; if the session is missing they redirect to /login
// and the spec fails loudly rather than silently shooting the login page.

export interface RouteSpec {
  /** Filesystem-safe name, used for screenshot filenames. */
  name: string
  path: string
  auth?: boolean
  /** Requires seeded data to resolve a real id/slug at runtime. */
  dynamic?: boolean
}

export const ROUTES: RouteSpec[] = [
  // ---- public ----
  { name: 'home', path: '/' },
  { name: 'login', path: '/login' },
  { name: 'models', path: '/models' },
  { name: 'status', path: '/status' },
  { name: 'api-reference', path: '/api-reference' },
  { name: 'blog', path: '/blog' },
  { name: 'docs', path: '/docs' },
  { name: 'privacy', path: '/privacy-policy' },
  { name: 'terms', path: '/terms-of-service' },
  { name: 'profile', path: '/designbot' },
  { name: 'profile-collection', path: '/designbot/collections/:slug', dynamic: true },
  { name: 'profile-cluster', path: '/designbot/cluster' },
  { name: 'register', path: '/register' },
  { name: 'confirm', path: '/confirm' },
  { name: 'blog-post', path: '/blog/introducing-inference-club' },
  { name: 'docs-page', path: '/docs/quickstart' },

  // ---- dashboard (auth) ----
  { name: 'dashboard', path: '/dashboard', auth: true },
  { name: 'requests', path: '/dashboard/inference/requests', auth: true },
  { name: 'requests-all', path: '/dashboard/inference/requests/all', auth: true },
  { name: 'request-detail', path: '/dashboard/inference/requests/:id', auth: true, dynamic: true },
  { name: 'gallery', path: '/dashboard/inference/gallery', auth: true },
  { name: 'bookmarks', path: '/dashboard/inference/bookmarks', auth: true },
  { name: 'starred', path: '/dashboard/inference/starred', auth: true },
  { name: 'collections', path: '/dashboard/inference/collections', auth: true },
  { name: 'collection-detail', path: '/dashboard/inference/collections/:slug', auth: true, dynamic: true },
  { name: 'music', path: '/dashboard/music', auth: true },
  { name: 'videos', path: '/dashboard/watch', auth: true },
  { name: 'watch', path: '/dashboard/watch/:videoId', auth: true, dynamic: true },
  { name: 'watch-playlist', path: '/dashboard/watch/:videoId?list=:slug', auth: true, dynamic: true },
  { name: 'leaderboard', path: '/dashboard/leaderboard', auth: true },
  { name: 'manifest', path: '/dashboard/manifest', auth: true },
  { name: 'models-dash', path: '/dashboard/models', auth: true },
  { name: 'playground', path: '/dashboard/playground', auth: true },
  { name: 'playground-images', path: '/dashboard/playground/images', auth: true },
  { name: 'playground-music', path: '/dashboard/playground/music', auth: true },
  { name: 'playground-model3d', path: '/dashboard/playground/model3d', auth: true },
  { name: 'playground-speech', path: '/dashboard/playground/speech', auth: true },
  { name: 'playground-transcribe', path: '/dashboard/playground/transcribe', auth: true },
  { name: 'playground-videos', path: '/dashboard/playground/videos', auth: true },
  { name: 'providers-all', path: '/dashboard/providers/all-nodes', auth: true },
  { name: 'providers-mine', path: '/dashboard/providers/my-nodes', auth: true },
  { name: 'settings-general', path: '/dashboard/settings/general', auth: true },
  { name: 'settings-access', path: '/dashboard/settings/access', auth: true },
  { name: 'settings-routing', path: '/dashboard/settings/routing', auth: true },
  { name: 'settings-token', path: '/dashboard/settings/token', auth: true },
  { name: 'settings-usage', path: '/dashboard/settings/usage', auth: true },
  { name: 'admin-activity', path: '/dashboard/admin/activity', auth: true },
  { name: 'admin-moderation', path: '/dashboard/admin/moderation', auth: true },
  { name: 'admin-access', path: '/dashboard/admin/access', auth: true },
  { name: 'admin-roadmap', path: '/dashboard/admin/roadmap', auth: true },
  { name: 'api-reference-dash', path: '/dashboard/api-reference', auth: true },
  { name: 'chats', path: '/dashboard/chats', auth: true },
  { name: 'chat-detail', path: '/dashboard/chats/:threadId', auth: true, dynamic: true },
  { name: 'cluster', path: '/dashboard/cluster', auth: true },
  { name: 'control', path: '/dashboard/control', auth: true },
  { name: 'media', path: '/dashboard/media', auth: true },
  { name: 'playground-agent', path: '/dashboard/playground/agent', auth: true },
  { name: 'playground-enhance', path: '/dashboard/playground/enhance', auth: true },
  { name: 'playground-image-to-video', path: '/dashboard/playground/image-to-video', auth: true },
  { name: 'playground-scrape', path: '/dashboard/playground/scrape', auth: true },
  { name: 'playground-voice-cloning', path: '/dashboard/playground/voice-cloning', auth: true },
  { name: 'playground-voice', path: '/dashboard/playground/voice', auth: true },
  { name: 'queue', path: '/dashboard/queue', auth: true },
  { name: 'queue-run', path: '/dashboard/queue/runs/:runId', auth: true, dynamic: true },
  { name: 'settings-api-keys', path: '/dashboard/settings/api-keys', auth: true },
  { name: 'settings-fallback', path: '/dashboard/settings/fallback', auth: true },
  { name: 'studio', path: '/dashboard/studio', auth: true },
  { name: 'studio-episode', path: '/dashboard/studio/:episodeId', auth: true, dynamic: true },
  { name: 'workflows', path: '/dashboard/workflows', auth: true },
  { name: 'workflow-new', path: '/dashboard/workflows/new', auth: true },
  { name: 'workflow-edit', path: '/dashboard/workflows/:workflowId/edit', auth: true, dynamic: true },

  // ---- design gallery (dev/staff) ----
  { name: 'design', path: '/design', auth: true },
  { name: 'design-cards', path: '/design/cards', auth: true },
  { name: 'design-primitives', path: '/design/primitives', auth: true },
  { name: 'design-logo', path: '/design/logo', auth: true },
  { name: 'design-cluster', path: '/design/cluster', auth: true },
  { name: 'design-cluster-assets', path: '/design/cluster-assets', auth: true },
  { name: 'design-logo-2d', path: '/design/logo-2d', auth: true },
]
