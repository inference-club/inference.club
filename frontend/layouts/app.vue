<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Sun, Moon } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

const { t } = useI18n()
const { isDark, toggleTheme } = useTheme()
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <header class="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
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
        <slot />
      </div>
      <DashboardFooter />
    </SidebarInset>
  </SidebarProvider>
</template>
