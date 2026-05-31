import { BookOpen, Boxes, Cpu, Send, Settings2, Sparkles, Trophy } from 'lucide-vue-next'
import type { Component } from 'vue'

export interface DashboardNavItem {
  title: string
  url: string
}

export interface DashboardNavGroup {
  title: string
  icon: Component
  items: DashboardNavItem[]
}

// Single source of truth for the dashboard sidebar AND the breadcrumbs, so the
// two never drift apart.
export const dashboardNav: DashboardNavGroup[] = [
  {
    title: 'Playground',
    icon: Sparkles,
    items: [
      { title: 'Chat', url: '/dashboard/playground' },
      { title: 'Transcription', url: '/dashboard/playground/transcribe' },
      { title: 'Images', url: '/dashboard/playground/images' },
    ],
  },
  {
    title: 'Models',
    icon: Boxes,
    items: [
      { title: 'Catalog', url: '/dashboard/models' },
    ],
  },
  {
    title: 'Inference Requests',
    icon: Send,
    items: [
      { title: 'Your requests', url: '/dashboard/inference/requests' },
      { title: 'All requests', url: '/dashboard/inference/requests/all' },
    ],
  },
  {
    title: 'Leaderboard',
    icon: Trophy,
    items: [
      { title: 'Token usage', url: '/dashboard/leaderboard' },
    ],
  },
  {
    title: 'Compute',
    icon: Cpu,
    items: [
      { title: 'My nodes', url: '/dashboard/providers/my-nodes' },
      { title: 'All nodes', url: '/dashboard/providers/all-nodes' },
      { title: 'Manifests', url: '/dashboard/manifest' },
    ],
  },
  {
    title: 'Documentation',
    icon: BookOpen,
    items: [
      { title: 'Introduction', url: '/docs/introduction' },
      { title: 'Get Started', url: '/docs/get-started' },
    ],
  },
  {
    title: 'Settings',
    icon: Settings2,
    items: [
      { title: 'General', url: '/dashboard/settings/general' },
      { title: 'Routing', url: '/dashboard/settings/routing' },
      { title: 'Usage', url: '/dashboard/settings/usage' },
      { title: 'Access', url: '/dashboard/settings/access' },
      { title: 'Token', url: '/dashboard/settings/token' },
    ],
  },
]
