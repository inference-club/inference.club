<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { useRoute } from 'vue-router'

import {
  BookOpen,
  Cpu,
  GalleryVerticalEnd,
  Send,
  Settings2,
} from 'lucide-vue-next'

const route = useRoute()
const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: 'icon',
})

const teams = [
  {
    name: 'inference.club',
    logo: GalleryVerticalEnd,
    plan: 'free account',
  },
]

const navMain = [
  {
    title: 'Inference Requests',
    icon: Send,
    items: [
      {
        title: 'List Requests',
        url: '/dashboard/inference/requests',
      },
    ],
  },
  {
    title: 'Compute',
    icon: Cpu,
    items: [
      {
        title: 'My nodes',
        url: '/dashboard/providers/my-nodes',
      },
      {
        title: 'All nodes',
        url: '/dashboard/providers/all-nodes',
      },
    ],
  },
  {
    title: 'Documentation',
    icon: BookOpen,
    items: [
      {
        title: 'Introduction',
        url: '/docs/introduction',
      },
      {
        title: 'Get Started',
        url: '/docs/get-started',
      },
    ],
  },
  {
    title: 'Settings',
    icon: Settings2,
    items: [
      {
        title: 'General',
        url: '/dashboard/settings/general',
      },
      {
        title: 'Token',
        url: '/dashboard/settings/token',
      },
    ],
  },
]

const isRouteActive = (url: string) => route.path.startsWith(url)

const navMainWithActive = navMain.map(item => ({
  ...item,
  isActive: item.items.some(s => isRouteActive(s.url)),
  items: item.items.map(subItem => ({
    ...subItem,
    isActive: isRouteActive(subItem.url),
  })),
}))
</script>

<template>
  <Sidebar v-bind="props">
    <SidebarHeader>
      <TeamSwitcher :teams="teams" />
    </SidebarHeader>
    <SidebarContent>
      <NavMain :items="navMainWithActive" />
    </SidebarContent>
    <SidebarFooter>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
