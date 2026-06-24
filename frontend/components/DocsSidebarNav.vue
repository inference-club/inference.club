<script setup lang="ts">
// Grouped docs navigation, shared by the desktop sidebar and the mobile drawer.
import type { DocsNavSection } from '@/composables/useDocsNav'

defineProps<{ sections: DocsNavSection[] }>()
const emit = defineEmits<{ navigate: [] }>()

const localePath = useLocalePath()
const route = useRoute()
// Stored paths are locale-free (/docs/x); compare against the localized form so
// the active item highlights under a locale prefix (/fr/docs/x).
const isActive = (path: string) => route.path === localePath(path)
</script>

<template>
  <nav class="text-sm">
    <div v-for="section in sections" :key="section.title" class="mb-6 last:mb-0">
      <p class="mb-2 px-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground/80">
        {{ section.title }}
      </p>
      <ul class="space-y-0.5">
        <li v-for="item in section.items" :key="item.path">
          <NuxtLink
            :to="localePath(item.path)"
            class="relative block rounded-md py-1.5 pl-3.5 pr-2 transition-colors"
            :class="isActive(item.path)
              ? 'font-medium text-foreground before:absolute before:left-0 before:top-1/2 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-primary bg-accent/60'
              : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'"
            @click="emit('navigate')"
          >
            {{ item.title }}
          </NuxtLink>
        </li>
      </ul>
    </div>
  </nav>
</template>
