<template>
  <div
    class="not-prose mb-6 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.07] px-4 py-2.5 text-sm text-amber-700 dark:text-amber-300"
  >
    <Info class="h-4 w-4 shrink-0" />
    <span>{{ t('content.fallbackNotice', { language: currentLanguageName }) }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Info } from 'lucide-vue-next'

// Shown above blog/docs content when the active locale has no translation and
// we're rendering the English version instead.
const { t, locale, locales } = useI18n()

const currentLanguageName = computed(() => {
  const match = (locales.value as Array<{ code: string, name?: string }>)
    .find(l => l.code === locale.value)
  return match?.name ?? String(locale.value)
})
</script>
