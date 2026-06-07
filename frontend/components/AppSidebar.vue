<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { dashboardNav } from '@/composables/useDashboardNav'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const localePath = useLocalePath()
const { user } = useAuth()
const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: 'icon',
})

// nav urls are locale-free (/dashboard/x); compare against the localized form so
// the active item resolves under a locale prefix (/fr/dashboard/x).
const isRouteActive = (url: string) => route.path.startsWith(localePath(url))

// Staff-only groups (e.g. Admin) are hidden from non-staff. The backend still
// enforces access; this only removes the affordance.
const navMainWithActive = computed(() =>
  dashboardNav
    .filter(group => !group.staffOnly || user.value?.is_staff)
    .map(item => ({
      ...item,
      isActive: item.items.some(s => isRouteActive(s.url)),
      items: item.items.map(subItem => ({
        ...subItem,
        isActive: isRouteActive(subItem.url),
      })),
    })),
)
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
