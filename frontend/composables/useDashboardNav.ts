import { BookOpen, Boxes, Cpu, Send, Settings2, ShieldCheck, Sparkles, Trophy } from 'lucide-vue-next'
import type { Component } from 'vue'

export interface DashboardNavItem {
  // i18n key resolved with t() at render time (e.g. 'dashboard.items.chat').
  titleKey: string
  url: string
}

export interface DashboardNavGroup {
  titleKey: string
  icon: Component
  items: DashboardNavItem[]
  // When true, the group is only rendered for staff users (filtered in
  // AppSidebar against the auth store). The API enforces staff access too —
  // this is purely to hide the affordance from non-staff.
  staffOnly?: boolean
}

// Single source of truth for the dashboard sidebar AND the breadcrumbs, so the
// two never drift apart. Titles are i18n keys (not literals) so both surfaces
// localize from one place; matching is by `url`, which stays locale-free.
export const dashboardNav: DashboardNavGroup[] = [
  {
    titleKey: 'dashboard.groups.playground',
    icon: Sparkles,
    items: [
      { titleKey: 'dashboard.items.chat', url: '/dashboard/playground' },
      { titleKey: 'dashboard.items.transcription', url: '/dashboard/playground/transcribe' },
      { titleKey: 'dashboard.items.images', url: '/dashboard/playground/images' },
      { titleKey: 'dashboard.items.imageTo3d', url: '/dashboard/playground/model3d' },
      { titleKey: 'dashboard.items.textToSpeech', url: '/dashboard/playground/speech' },
      { titleKey: 'dashboard.items.musicGeneration', url: '/dashboard/playground/music' },
    ],
  },
  {
    titleKey: 'dashboard.groups.models',
    icon: Boxes,
    items: [
      { titleKey: 'dashboard.items.catalog', url: '/dashboard/models' },
    ],
  },
  {
    titleKey: 'dashboard.groups.inferenceRequests',
    icon: Send,
    items: [
      { titleKey: 'dashboard.items.yourRequests', url: '/dashboard/inference/requests' },
      { titleKey: 'dashboard.items.allRequests', url: '/dashboard/inference/requests/all' },
      { titleKey: 'dashboard.items.gallery', url: '/dashboard/inference/gallery' },
      { titleKey: 'dashboard.items.starred', url: '/dashboard/inference/starred' },
      { titleKey: 'dashboard.items.bookmarks', url: '/dashboard/inference/bookmarks' },
      { titleKey: 'dashboard.items.collections', url: '/dashboard/inference/collections' },
    ],
  },
  {
    titleKey: 'dashboard.groups.leaderboard',
    icon: Trophy,
    items: [
      { titleKey: 'dashboard.items.tokenUsage', url: '/dashboard/leaderboard' },
    ],
  },
  {
    titleKey: 'dashboard.groups.compute',
    icon: Cpu,
    items: [
      { titleKey: 'dashboard.items.myNodes', url: '/dashboard/providers/my-nodes' },
      { titleKey: 'dashboard.items.allNodes', url: '/dashboard/providers/all-nodes' },
      { titleKey: 'dashboard.items.manifests', url: '/dashboard/manifest' },
    ],
  },
  {
    titleKey: 'dashboard.groups.documentation',
    icon: BookOpen,
    items: [
      { titleKey: 'dashboard.items.introduction', url: '/docs/introduction' },
      { titleKey: 'dashboard.items.getStarted', url: '/docs/get-started' },
      { titleKey: 'dashboard.items.apiReference', url: '/dashboard/api-reference' },
    ],
  },
  {
    titleKey: 'dashboard.groups.settings',
    icon: Settings2,
    items: [
      { titleKey: 'dashboard.items.general', url: '/dashboard/settings/general' },
      { titleKey: 'dashboard.items.routing', url: '/dashboard/settings/routing' },
      { titleKey: 'dashboard.items.usage', url: '/dashboard/settings/usage' },
      { titleKey: 'dashboard.items.access', url: '/dashboard/settings/access' },
      { titleKey: 'dashboard.items.token', url: '/dashboard/settings/token' },
    ],
  },
  {
    titleKey: 'dashboard.groups.admin',
    icon: ShieldCheck,
    staffOnly: true,
    items: [
      { titleKey: 'dashboard.items.activity', url: '/dashboard/admin/activity' },
      { titleKey: 'dashboard.items.moderation', url: '/dashboard/admin/moderation' },
    ],
  },
]
