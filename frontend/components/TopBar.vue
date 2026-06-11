<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="flex h-14 items-center px-4 sm:px-6 lg:px-8">
      <div class="mr-2 sm:mr-4 flex min-w-0">
        <NuxtLink :to="localePath('/')" class="mr-0 sm:mr-6 flex min-w-0 items-center gap-1.5 sm:gap-2">
          <AppLogo class="size-5 sm:size-6 shrink-0 text-primary" />
          <span class="whitespace-nowrap font-bold text-sm sm:text-xl">inference.club</span>
        </NuxtLink>
        <nav class="hidden md:flex items-center space-x-4 text-sm">
          <NuxtLink
            v-if="isAuthenticated"
            :to="localePath('/dashboard')"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            {{ t('nav.dashboard') }}
          </NuxtLink>
          <NuxtLink
            :to="localePath('/status')"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            {{ t('nav.network') }}
          </NuxtLink>
          <NuxtLink
            :to="localePath('/docs')"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            {{ t('nav.docs') }}
          </NuxtLink>
          <NuxtLink
            :to="localePath('/blog')"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            {{ t('nav.blog') }}
          </NuxtLink>
        </nav>
      </div>
      <div class="flex flex-1 shrink-0 items-center justify-end gap-0.5 sm:gap-2">
        <LanguagePicker />

        <Button variant="ghost" size="sm" class="px-1.5 sm:px-2" @click="toggleTheme">
          <Sun v-if="isDark" class="h-5 w-5" />
          <Moon v-else class="h-5 w-5" />
          <span class="sr-only">{{ t('nav.toggleTheme') }}</span>
        </Button>

        <!-- Show login button if not authenticated -->
        <Button v-if="!isAuthenticated" variant="ghost" size="sm" class="px-1.5 sm:px-2">
          <NuxtLink :to="localePath('/login')">{{ t('nav.login') }}</NuxtLink>
        </Button>

        <!-- Show logout button with popover if authenticated -->
        <Popover v-else>
          <PopoverTrigger as-child>
            <Button variant="ghost" size="sm">
              <User class="h-5 w-5" />
              <span class="sr-only">{{ t('nav.userMenu') }}</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent class="w-56" align="end">
            <div class="flex flex-col gap-1">
              <div class="px-2 py-1.5">
                <div class="text-sm font-medium truncate">
                  {{ user?.github_login || user?.email }}
                </div>
                <div v-if="user?.github_login && user?.email" class="text-xs text-muted-foreground truncate">
                  {{ user.email }}
                </div>
              </div>
              <Separator />
              <Button
                v-if="user?.github_login"
                as-child
                variant="ghost"
                class="justify-start"
              >
                <NuxtLink :to="localePath(`/${user.github_login}`)">
                  <UserRound class="mr-2 h-4 w-4" />
                  {{ t('nav.publicProfile') }}
                </NuxtLink>
              </Button>
              <Button as-child variant="ghost" class="justify-start">
                <NuxtLink :to="localePath('/dashboard/settings/general')">
                  <Settings class="mr-2 h-4 w-4" />
                  {{ t('nav.accountSettings') }}
                </NuxtLink>
              </Button>
              <Separator />
              <Button
                variant="ghost"
                class="justify-start text-red-600 hover:text-red-700 hover:bg-red-50"
                @click="logout"
              >
                <LogOut class="mr-2 h-4 w-4" />
                {{ t('nav.logout') }}
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Sun, Moon, User, LogOut, UserRound, Settings } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()
const localePath = useLocalePath()
const { isDark, toggleTheme } = useTheme()
const { user, isAuthenticated, logout } = useAuth()
</script>