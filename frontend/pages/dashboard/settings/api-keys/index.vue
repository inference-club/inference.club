<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { toast } from 'vue-sonner'
import { KeyRound, ExternalLink, Check, Loader2, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useApiKeys, type ApiKeyInfo } from '@/composables/useApiKeys'

definePageMeta({ layout: 'app', requireMember: true, gateTitleKey: 'dashboard.items.apiKeys' })

const { list, setKey, clearKey } = useApiKeys()

const services = ref<ApiKeyInfo[]>([])
const loading = ref(true)
const loadError = ref('')
// Per-service input + in-flight state.
const drafts = reactive<Record<string, string>>({})
const saving = reactive<Record<string, boolean>>({})

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    services.value = await list()
  } catch (e) {
    loadError.value = (e as Error)?.message || 'Failed to load API keys'
  } finally {
    loading.value = false
  }
}

const save = async (svc: ApiKeyInfo) => {
  const value = (drafts[svc.service] || '').trim()
  if (!value) return
  saving[svc.service] = true
  try {
    await setKey(svc.service, value)
    drafts[svc.service] = ''
    toast.success(`${svc.name} key saved`)
    await load()
  } catch {
    toast.error(`Failed to save ${svc.name} key`)
  } finally {
    saving[svc.service] = false
  }
}

const remove = async (svc: ApiKeyInfo) => {
  if (!confirm(`Remove your ${svc.name} key?`)) return
  saving[svc.service] = true
  try {
    await clearKey(svc.service)
    toast.success(`${svc.name} key removed`)
    await load()
  } catch {
    toast.error(`Failed to remove ${svc.name} key`)
  } finally {
    saving[svc.service] = false
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto w-full max-w-2xl px-3 sm:px-6 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <KeyRound class="size-6" /> API keys
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        Store keys for external services. They're encrypted, never shown again, and shared
        across every agent that runs as you — the text agent, the voice agent, and future tools.
      </p>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="h-28 rounded-lg border bg-muted/30 animate-pulse" />
    </div>
    <div v-else-if="loadError" class="text-destructive text-sm py-6">{{ loadError }}</div>

    <div v-else class="space-y-4">
      <div v-for="svc in services" :key="svc.service" class="rounded-lg border p-4">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h2 class="font-medium flex items-center gap-2">
              {{ svc.name }}
              <span
                v-if="svc.is_set"
                class="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400"
              >
                <Check class="size-3" /> set <span class="font-mono text-muted-foreground">{{ svc.hint }}</span>
              </span>
              <span v-else class="text-[11px] text-muted-foreground">not set</span>
            </h2>
            <p class="text-sm text-muted-foreground mt-0.5">{{ svc.description }}</p>
          </div>
          <a
            v-if="svc.docs_url"
            :href="svc.docs_url"
            target="_blank"
            rel="noopener"
            class="shrink-0 inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Get a key <ExternalLink class="size-3" />
          </a>
        </div>

        <div class="mt-3 flex items-center gap-2">
          <input
            v-model="drafts[svc.service]"
            type="password"
            autocomplete="off"
            :placeholder="svc.is_set ? 'Replace key…' : 'Paste key…'"
            class="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm font-mono"
            @keydown.enter="save(svc)"
          />
          <Button size="sm" :disabled="saving[svc.service] || !(drafts[svc.service] || '').trim()" @click="save(svc)">
            <Loader2 v-if="saving[svc.service]" class="mr-1 size-3.5 animate-spin" />
            {{ svc.is_set ? 'Replace' : 'Save' }}
          </Button>
          <Button
            v-if="svc.is_set"
            size="icon"
            variant="ghost"
            class="size-8 text-muted-foreground hover:text-destructive"
            :disabled="saving[svc.service]"
            title="Remove key"
            @click="remove(svc)"
          >
            <Trash2 class="size-4" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
