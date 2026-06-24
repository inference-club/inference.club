<script setup lang="ts">
import { BookText, Menu, X, ChevronRight } from 'lucide-vue-next'
import TopBar from '@/components/TopBar.vue'

const localePath = useLocalePath()
const route = useRoute()
// Grouped sections (by category) shared with prev/next via useDocsNav.
const { sections, flat } = await useDocsNav()

const isActive = (path: string) => route.path === localePath(path)
const current = computed(() => flat.value.find((i) => isActive(i.path)) ?? null)
const currentSection = computed(() =>
  sections.value.find((s) => s.items.some((i) => isActive(i.path))) ?? null,
)

// Mobile drawer
const drawerOpen = ref(false)
watch(() => route.path, () => { drawerOpen.value = false })
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <TopBar />

    <!-- Docs sub-bar: gives the docs its own chrome under the shared top bar. -->
    <div class="sticky top-14 z-30 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div class="flex h-11 items-center gap-2 px-4 sm:px-6 lg:px-8">
        <button
          class="-ml-1.5 flex items-center gap-1.5 rounded-md px-1.5 py-1 text-sm text-muted-foreground hover:text-foreground lg:hidden"
          @click="drawerOpen = true"
        >
          <Menu class="size-4" />
          <span class="font-medium">Menu</span>
        </button>
        <!-- Mobile: current page title -->
        <span class="min-w-0 flex-1 truncate text-sm font-medium lg:hidden">{{ current?.title ?? 'Documentation' }}</span>
        <!-- Desktop: breadcrumb -->
        <nav class="hidden items-center gap-1.5 text-sm lg:flex">
          <NuxtLink :to="localePath('/docs')" class="text-muted-foreground transition-colors hover:text-foreground">Docs</NuxtLink>
          <template v-if="currentSection">
            <ChevronRight class="size-3.5 text-muted-foreground/50" />
            <span class="text-muted-foreground">{{ currentSection.title }}</span>
          </template>
          <template v-if="current">
            <ChevronRight class="size-3.5 text-muted-foreground/50" />
            <span class="font-medium text-foreground">{{ current.title }}</span>
          </template>
        </nav>
      </div>
    </div>

    <div class="mx-auto flex w-full max-w-[88rem] flex-1">
      <!-- Desktop sidebar -->
      <aside class="hidden w-64 shrink-0 border-r lg:block">
        <div class="sticky top-[6.25rem] max-h-[calc(100vh-6.25rem)] overflow-y-auto px-5 py-7">
          <div class="mb-6 flex items-center gap-2 px-2">
            <span class="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BookText class="size-4" />
            </span>
            <span class="font-semibold tracking-tight">Documentation</span>
          </div>
          <DocsSidebarNav :sections="sections" />
        </div>
      </aside>

      <!-- Width + prose styling live in the pages so a doc page can put a table
           of contents beside the article. Tight margins on mobile. -->
      <main class="docs-content min-w-0 flex-1 break-words px-4 py-8 sm:px-6 lg:px-10">
        <slot />
      </main>
    </div>

    <!-- Mobile drawer -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        leave-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div v-if="drawerOpen" class="fixed inset-0 z-[60] bg-black/40 lg:hidden" @click="drawerOpen = false" />
      </Transition>
      <Transition
        enter-active-class="transition-transform duration-200 ease-out"
        leave-active-class="transition-transform duration-200 ease-in"
        enter-from-class="-translate-x-full"
        leave-to-class="-translate-x-full"
      >
        <aside
          v-if="drawerOpen"
          class="fixed inset-y-0 left-0 z-[61] flex w-[18rem] max-w-[85vw] flex-col border-r bg-background lg:hidden"
        >
          <div class="flex h-14 items-center justify-between border-b px-5">
            <div class="flex items-center gap-2">
              <span class="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <BookText class="size-4" />
              </span>
              <span class="font-semibold tracking-tight">Documentation</span>
            </div>
            <button class="rounded-md p-1 text-muted-foreground hover:text-foreground" @click="drawerOpen = false">
              <X class="size-5" />
            </button>
          </div>
          <div class="flex-1 overflow-y-auto px-5 py-6">
            <DocsSidebarNav :sections="sections" @navigate="drawerOpen = false" />
          </div>
        </aside>
      </Transition>
    </Teleport>
  </div>
</template>
