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

  // ---- design gallery (dev/staff) ----
  { name: 'design', path: '/design', auth: true },
  { name: 'design-cards', path: '/design/cards', auth: true },
  { name: 'design-primitives', path: '/design/primitives', auth: true },
]
