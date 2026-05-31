<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { useRoute } from 'vue-router'

import { dashboardNav } from '@/composables/useDashboardNav'

const route = useRoute()
const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: 'icon',
})

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
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            class="cursor-default hover:bg-transparent active:bg-transparent"
          >
            <div class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
              <AppLogo class="size-4" />
            </div>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-semibold">inference.club</span>
              <span class="truncate text-xs text-muted-foreground">free account</span>
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
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
