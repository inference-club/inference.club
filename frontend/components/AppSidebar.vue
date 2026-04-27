<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { useRoute } from 'vue-router'

import {
  BookOpen,
  Cpu,
  GalleryVerticalEnd,
  Moon,
  Send,
  Settings2,
  Sun,
} from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const { isDark, toggleTheme } = useTheme()
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
      {
        title: 'Manifests',
        url: '/dashboard/manifest',
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
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            :tooltip="isDark ? 'Switch to light' : 'Switch to dark'"
            @click="toggleTheme"
          >
            <Sun v-if="isDark" />
            <Moon v-else />
            <span>{{ isDark ? 'Light mode' : 'Dark mode' }}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
