<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="flex h-14 items-center px-4 sm:px-6 lg:px-8">
      <div class="mr-4 flex">
        <NuxtLink to="/" class="mr-6 flex items-center space-x-2">
          <span class="font-bold text-xl">inference.club</span>
        </NuxtLink>
        <nav class="hidden md:flex items-center space-x-4 text-sm">
          <NuxtLink
            to="/docs"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            Docs
          </NuxtLink>
          <NuxtLink
            to="/blog"
            class="text-muted-foreground transition-colors hover:text-foreground"
          >
            Blog
          </NuxtLink>
        </nav>
      </div>
      <div class="flex flex-1 items-center justify-end space-x-2">
        <Button variant="ghost" size="sm" @click="toggleTheme">
          <Sun v-if="isDark" class="h-5 w-5" />
          <Moon v-else class="h-5 w-5" />
          <span class="sr-only">Toggle theme</span>
        </Button>

        <!-- Show login button if not authenticated -->
        <Button v-if="!isAuthenticated" variant="ghost" size="sm">
          <NuxtLink to="/login">Login</NuxtLink>
        </Button>

        <!-- Show logout button with popover if authenticated -->
        <Popover v-else>
          <PopoverTrigger as-child>
            <Button variant="ghost" size="sm">
              <User class="h-5 w-5" />
              <span class="sr-only">User menu</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent class="w-56">
            <div class="flex flex-col gap-2">
              <div class="text-sm font-medium">{{ user?.email }}</div>
              <Separator />
              <Button
                variant="ghost"
                class="justify-start text-red-600 hover:text-red-700 hover:bg-red-50"
                @click="logout"
              >
                <LogOut class="mr-2 h-4 w-4" />
                Logout
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
import { Sun, Moon, User, LogOut } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'

const { isDark, toggleTheme } = useTheme()
const { user, isAuthenticated, logout } = useAuth()
</script>