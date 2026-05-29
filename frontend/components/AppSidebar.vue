<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { useRoute } from 'vue-router'

import {
  GalleryVerticalEnd,
  Moon,
  Sun,
} from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { dashboardNav } from '@/composables/useDashboardNav'

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

const isRouteActive = (url: string) => route.path.startsWith(url)

const navMainWithActive = dashboardNav.map(item => ({
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
