<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { useRoute } from 'vue-router'

import {
  BookOpen,
  Bot,
  GalleryVerticalEnd,
  Settings2,
} from 'lucide-vue-next'

const route = useRoute()
const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: 'icon',
})

// This is sample data.
const data = {
  user: {
    name: 'shadcn',
    email: 'm@example.com',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: 'inference.club',
      logo: GalleryVerticalEnd,
      plan: 'free account',
    }
  ],
  navMain: [
    {
      title: 'Inference Providers',
      url: '/providers',
      icon: Bot,
      items: [
        {
          title: 'My nodes',
          url: '/providers/my-nodes',
        },
        {
          title: 'All nodes',
          url: '/providers/all-nodes',
        },
        {
          title: 'Settings',
          url: '/providers/settings',
        },
      ],
    },
    {
      title: 'Models',
      url: '/models',
      icon: Bot,
      items: [
        {
          title: 'Genesis',
          url: '/models/genesis',
        },
        {
          title: 'Explorer',
          url: '/models/explorer',
        },
        {
          title: 'Quantum',
          url: '/models/quantum',
        },
      ],
    },
    {
      title: 'Documentation',
      url: '/docs',
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
        {
          title: 'Tutorials',
          url: '/docs/tutorials',
        },
        {
          title: 'Changelog',
          url: '/docs/changelog',
        },
      ],
    },
    {
      title: 'Settings',
      url: '/settings',
      icon: Settings2,
      items: [
        {
          title: 'General',
          url: '/settings/general',
        },
        {
          title: 'Team',
          url: '/settings/team',
        },
        {
          title: 'Billing',
          url: '/settings/billing',
        },
        {
          title: 'Limits',
          url: '/settings/limits',
        },
      ],
    },
  ],
}

// Function to check if a route is active
const isRouteActive = (url: string) => {
  return route.path.startsWith(url)
}

// Update the navMain items to include isActive
const navMainWithActive = data.navMain.map(item => ({
  ...item,
  isActive: isRouteActive(item.url),
  items: item.items.map(subItem => ({
    ...subItem,
    isActive: isRouteActive(subItem.url)
  }))
}))
</script>

<template>
  <Sidebar v-bind="props">
    <SidebarHeader>
      <TeamSwitcher :teams="data.teams" />
    </SidebarHeader>
    <SidebarContent>
      <NavMain :items="navMainWithActive" />
      <!-- <NavProjects :projects="data.projects" /> -->
    </SidebarContent>
    <SidebarFooter>
      <NavUser :user="data.user" />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
