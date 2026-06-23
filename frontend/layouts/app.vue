<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Sun, Moon } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { usePlayerStore } from '@/stores/player'
import { useAuth } from '@/composables/useAuth'

const { t } = useI18n()
const { isDark, toggleTheme } = useTheme()
const player = usePlayerStore()
const route = useRoute()
const { isAuthenticated, isAnonymous, ready } = useAuth()

// Page-level gating, declared per page via definePageMeta:
//   requireAuth: true   → any signed-in account (guests included) may enter;
//                         logged-out visitors get the JoinGate funnel.
//   requireMember: true → full members only; logged-out → JoinGate,
//                         guests → MemberOnlyGate (the upgrade prompt).
// The API enforces all of this too — this just turns broken 401 shells into an
// inviting sign-in surface, and (by rendering the gate *instead of* <slot/>)
// stops the page's owner-scoped fetches from firing for visitors who can't see
// the data anyway.
const meta = computed(() => route.meta as {
  requireAuth?: boolean
  requireMember?: boolean
  gateTitleKey?: string
  gateDescKey?: string
})

const isGated = computed(() => !!meta.value.requireAuth || !!meta.value.requireMember)

// 'none' → render the page. Otherwise show a gate (or a skeleton until the
// initial auth check resolves, so we never flash a gate at a logged-in user).
const gateMode = computed<'none' | 'skeleton' | 'auth' | 'member'>(() => {
  if (!isGated.value) return 'none'
  if (!ready.value) return 'skeleton'
  if (!isAuthenticated.value) return 'auth'
  if (meta.value.requireMember && isAnonymous.value) return 'member'
  return 'none'
})

const gateTitle = computed(() =>
  meta.value.gateTitleKey ? t(meta.value.gateTitleKey) : t('gate.defaultTitle'),
)
const gateDescription = computed(() =>
  meta.value.gateDescKey ? t(meta.value.gateDescKey) : t('gate.signInToUse'),
)
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset class="min-w-0">
      <header class="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
        <div class="flex flex-1 items-center gap-2 px-4">
          <SidebarTrigger class="-ml-1" />
          <Separator
            orientation="vertical"
            class="mr-2 data-[orientation=vertical]:h-4"
          />
          <DashboardBreadcrumbs />
          <!-- Right-aligned controls. The wrapper carries ml-auto because
               LanguagePicker's root is a renderless Reka <Popover> (no DOM
               node), so a class on it would be dropped. -->
          <div class="ml-auto flex items-center gap-2">
            <LanguagePicker />
            <Button
              variant="ghost"
              size="icon"
              :title="isDark ? t('dashboard.switchToLight') : t('dashboard.switchToDark')"
              @click="toggleTheme"
            >
              <Sun v-if="isDark" class="h-5 w-5" />
              <Moon v-else class="h-5 w-5" />
              <span class="sr-only">{{ t('nav.toggleTheme') }}</span>
            </Button>
          </div>
        </div>
      </header>
      <div class="flex flex-1 flex-col gap-4 p-4 pt-0">
        <AnonymousBanner />
        <LoggedOutBanner v-if="gateMode === 'none'" />
        <JoinGate
          v-if="gateMode === 'auth'"
          :title="gateTitle"
          :description="gateDescription"
        />
        <MemberOnlyGate
          v-else-if="gateMode === 'member'"
          :title="gateTitle"
          :description="t('gate.memberDescription')"
        />
        <div v-else-if="gateMode === 'skeleton'" class="space-y-4">
          <div class="h-8 w-48 animate-pulse rounded bg-muted" />
          <div class="h-48 animate-pulse rounded-xl bg-muted" />
        </div>
        <slot v-else />
      </div>
      <DashboardFooter />
      <!-- Spacer so the fixed player bar never covers page content. -->
      <div v-if="player.hasQueue" class="h-20 shrink-0" />
    </SidebarInset>
    <GlobalPlayerBar />
  </SidebarProvider>
</template>
