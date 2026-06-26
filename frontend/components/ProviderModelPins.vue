<script setup lang="ts">
// Browse an external provider's catalog and pin the models you want in the
// picker. Rendered inside each LLM-provider card on the API-keys page (PRD 19).
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Pin, PinOff, Search } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useExternalProviders, type CatalogModel } from '@/composables/useExternalProviders'

const props = defineProps<{ slug: string; label: string }>()

const { browse, pin, unpin } = useExternalProviders()

const open = ref(false)
const query = ref('')
const models = ref<CatalogModel[]>([])
const loading = ref(false)
const error = ref('')
const busy = ref<Record<string, boolean>>({})
const loadedOnce = ref(false)

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    models.value = await browse(props.slug, query.value.trim())
    loadedOnce.value = true
  } catch (e) {
    error.value = (e as Error)?.message || 'Could not load models'
  } finally {
    loading.value = false
  }
}

const toggleOpen = () => {
  open.value = !open.value
  if (open.value && !loadedOnce.value) load()
}

const toggle = async (m: CatalogModel) => {
  busy.value[m.model_id] = true
  try {
    if (m.pinned) {
      await unpin(props.slug, m.model_id)
      m.pinned = false
    } else {
      await pin(props.slug, m)
      m.pinned = true
      toast.success(`Pinned ${m.display_name}`)
    }
  } catch (e) {
    toast.error((e as Error)?.message || 'Could not update pin')
  } finally {
    busy.value[m.model_id] = false
  }
}

const pinnedCount = () => models.value.filter((m) => m.pinned).length
</script>

<template>
  <div class="mt-3 border-t pt-3">
    <button
      type="button"
      class="flex w-full items-center justify-between text-sm font-medium text-muted-foreground hover:text-foreground"
      @click="toggleOpen"
    >
      <span class="inline-flex items-center gap-1.5"><Pin class="size-3.5" /> Browse &amp; pin models</span>
      <span v-if="loadedOnce && pinnedCount()" class="text-xs">{{ pinnedCount() }} pinned</span>
    </button>

    <div v-if="open" class="mt-3">
      <div class="flex items-center gap-2">
        <div class="relative flex-1">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            v-model="query"
            type="text"
            :placeholder="`Search ${label} models…`"
            class="w-full rounded-md border bg-background py-1.5 pl-8 pr-3 text-sm"
            @keydown.enter="load"
          />
        </div>
        <Button size="sm" variant="outline" :disabled="loading" @click="load">
          <Loader2 v-if="loading" class="mr-1 size-3.5 animate-spin" />
          Search
        </Button>
      </div>

      <p v-if="error" class="mt-2 text-xs text-destructive">{{ error }}</p>

      <div v-else class="mt-2 max-h-72 space-y-1 overflow-y-auto">
        <p v-if="!loading && !models.length" class="py-3 text-center text-xs text-muted-foreground">
          No models found.
        </p>
        <div
          v-for="m in models"
          :key="m.model_id"
          class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/50"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate font-mono text-xs">{{ m.model_id }}</div>
          </div>
          <span v-if="m.context_length" class="shrink-0 text-[11px] text-muted-foreground">
            {{ Math.round(m.context_length / 1000) }}K
          </span>
          <Button
            size="sm"
            :variant="m.pinned ? 'secondary' : 'ghost'"
            class="h-7 shrink-0 gap-1 px-2 text-xs"
            :disabled="busy[m.model_id]"
            @click="toggle(m)"
          >
            <Loader2 v-if="busy[m.model_id]" class="size-3 animate-spin" />
            <component :is="m.pinned ? PinOff : Pin" v-else class="size-3" />
            {{ m.pinned ? 'Unpin' : 'Pin' }}
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
