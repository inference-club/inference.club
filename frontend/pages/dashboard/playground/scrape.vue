<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Globe, Loader2, Copy, Check, ExternalLink } from 'lucide-vue-next'
import { Card } from '@/components/ui/card'
import { useScrape, type ScrapeResult } from '@/composables/useScrape'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.scrape' })

const { listScrapeModels, scrape } = useScrape()

const models = ref<string[]>([])
const model = ref('')
const url = ref('')
const running = ref(false)
const error = ref<string | null>(null)
const result = ref<ScrapeResult | null>(null)
const loadError = ref<string | null>(null)
const copied = ref(false)

onMounted(async () => {
  try {
    models.value = await listScrapeModels()
    if (models.value.length) model.value = models.value[0]
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Failed to load models'
  }
})

const canRun = computed(() => !!model.value && !!url.value.trim() && !running.value)

const run = async () => {
  if (!canRun.value) return
  running.value = true
  error.value = null
  result.value = null
  try {
    result.value = await scrape(url.value.trim(), model.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Scrape failed'
  } finally {
    running.value = false
  }
}

useSubmitHotkey(run)

const copy = async () => {
  if (!result.value?.markdown) return
  try {
    await navigator.clipboard.writeText(result.value.markdown)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // clipboard may be unavailable; ignore
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-3 sm:px-6 py-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Globe class="size-6" /> Web scrape
      </h1>
      <p class="text-muted-foreground text-sm mt-1">
        Turn any URL into clean markdown via Firecrawl — the same
        <code class="text-xs">scrape</code> step that seeds the URL→video workflow.
      </p>
    </div>

    <Card class="p-4 space-y-3">
      <div v-if="loadError" class="text-destructive text-sm">{{ loadError }}</div>
      <div v-else-if="!models.length" class="text-muted-foreground text-sm">
        No web-scrape provider is online for your account yet.
      </div>

      <div v-if="models.length > 1" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground">Model</label>
        <select v-model="model" class="w-full rounded-md border bg-background px-3 py-2 text-sm">
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>

      <form class="flex gap-2" @submit.prevent="run">
        <input
          v-model="url"
          type="url"
          placeholder="https://example.com/an-article"
          class="flex-1 rounded-md border bg-background px-3 py-2 text-sm"
          :disabled="!models.length"
        >
        <button
          type="submit"
          :disabled="!canRun"
          class="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <Loader2 v-if="running" class="size-4 animate-spin" />
          {{ running ? 'Scraping…' : 'Scrape' }}
        </button>
      </form>

      <div v-if="error" class="text-destructive text-sm">{{ error }}</div>
    </Card>

    <Card v-if="result" class="p-4 space-y-3">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="font-semibold truncate">{{ result.title || 'Scraped document' }}</div>
          <a
            v-if="result.source_url" :href="result.source_url" target="_blank" rel="noopener"
            class="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          >
            <ExternalLink class="size-3" /> {{ result.source_url }}
          </a>
          <div class="text-xs text-muted-foreground mt-0.5">{{ result.chars.toLocaleString() }} chars</div>
        </div>
        <button
          class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted shrink-0"
          @click="copy"
        >
          <component :is="copied ? Check : Copy" class="size-3.5" />
          {{ copied ? 'Copied' : 'Copy markdown' }}
        </button>
      </div>
      <pre class="max-h-[28rem] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-words">{{ result.markdown }}</pre>
    </Card>
  </div>
</template>
