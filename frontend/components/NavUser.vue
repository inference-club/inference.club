<script setup lang="ts">
import {
  Avatar,
  AvatarFallback,
} from '@/components/ui/avatar'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import {
  ChevronsUpDown,
  Github,
  KeyRound,
  LogOut,
  Settings,
  Shield,
  UserRound,
  VenetianMask,
} from 'lucide-vue-next'
import { computed } from 'vue'
import { NuxtLink } from '#components'
import { useAuth } from '@/composables/useAuth'

const { user, logout, isAnonymous } = useAuth()
const { isMobile } = useSidebar()
const config = useRuntimeConfig()

// The handle is the canonical public identity (PRD 08); github_login is only
// shown to the owner in settings.
const handle = computed(() => user.value?.handle ?? user.value?.github_login ?? '')
const displayName = computed(() => handle.value || user.value?.email || 'Not signed in')
const isStaff = computed(() => !!user.value?.is_staff)
const profilePath = computed(() => (handle.value ? `/${handle.value}` : null))
const initials = computed(() => {
  const source = handle.value || (user.value?.email?.split('@')[0] ?? '')
  return (source.slice(0, 2) || '?').toUpperCase()
})

// "Keep this account": OAuth while logged in associates the GitHub identity
// with this anonymous account server-side (the upgrade pipeline).
const keepAccount = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}
</script>

<template>
  <SidebarMenu>
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <SidebarMenuButton
            size="lg"
            class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
          >
            <Avatar class="h-8 w-8 rounded-lg">
              <AvatarFallback class="rounded-lg">
                {{ initials }}
              </AvatarFallback>
            </Avatar>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="flex items-center gap-1 text-xs">
                <span class="truncate">{{ displayName }}</span>
                <Badge
                  v-if="isStaff"
                  variant="secondary"
                  class="h-4 shrink-0 gap-0.5 px-1 text-[10px] leading-none"
                  title="Staff"
                >
                  <Shield class="size-2.5" />
                  Staff
                </Badge>
                <Badge
                  v-if="isAnonymous"
                  variant="secondary"
                  class="h-4 shrink-0 gap-0.5 px-1 text-[10px] leading-none"
                  title="Anonymous account"
                >
                  <VenetianMask class="size-2.5" />
                  Anon
                </Badge>
              </span>
            </div>
            <ChevronsUpDown class="ml-auto size-4" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          class="w-[--reka-dropdown-menu-trigger-width] min-w-56 rounded-lg"
          :side="isMobile ? 'bottom' : 'right'"
          align="end"
          :side-offset="4"
        >
          <DropdownMenuLabel class="p-0 font-normal">
            <div class="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
              <Avatar class="h-8 w-8 rounded-lg">
                <AvatarFallback class="rounded-lg">
                  {{ initials }}
                </AvatarFallback>
              </Avatar>
              <div class="grid flex-1 text-left text-sm leading-tight">
                <span class="flex items-center gap-1 font-medium">
                  <span class="truncate">{{ displayName }}</span>
                  <Badge
                    v-if="isStaff"
                    variant="secondary"
                    class="h-4 shrink-0 gap-0.5 px-1 text-[10px] leading-none"
                  >
                    <Shield class="size-2.5" />
                    Staff
                  </Badge>
                </span>
                <span v-if="isAnonymous" class="truncate text-xs text-muted-foreground">Anonymous account</span>
                <span v-else-if="user?.email" class="truncate text-xs text-muted-foreground">{{ user.email }}</span>
              </div>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem v-if="profilePath" as-child>
              <NuxtLink :to="profilePath">
                <UserRound />
                {{ isAnonymous ? 'Unlisted profile' : 'Public profile' }}
              </NuxtLink>
            </DropdownMenuItem>
            <DropdownMenuItem as-child>
              <NuxtLink to="/dashboard/settings/general">
                <Settings />
                Account
              </NuxtLink>
            </DropdownMenuItem>
            <DropdownMenuItem v-if="!isAnonymous" as-child>
              <NuxtLink to="/dashboard/settings/token">
                <KeyRound />
                API token
              </NuxtLink>
            </DropdownMenuItem>
            <DropdownMenuItem v-if="isAnonymous" @click="keepAccount">
              <Github />
              Keep this account…
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem @click="logout">
            <LogOut />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
</template>
