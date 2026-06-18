<script setup lang="ts">
import { useSidebar, type SidebarProps } from '@/components/ui/sidebar'
import { computed, watch } from 'vue'
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

// On phones the sidebar is an overlay sheet that covers the page, so any
// navigation should dismiss it — otherwise the new page renders behind the
// menu. One watcher covers every link in the sidebar, present and future.
const { setOpenMobile } = useSidebar()
watch(() => route.fullPath, () => setOpenMobile(false))

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
          <SidebarMenuButton size="lg" as-child>
            <NuxtLink :to="localePath('/')">
              <div class="flex aspect-square size-9 items-center justify-center">
                <LogoJack3D :size="34" :speed="0.7" pose="upright" />
              </div>
              <div class="grid min-w-0 flex-1 text-left leading-tight">
                <span class="truncate text-lg font-semibold">inference.club</span>
              </div>
            </NuxtLink>
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
