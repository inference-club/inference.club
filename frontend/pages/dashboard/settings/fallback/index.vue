<script setup lang="ts">
// Pick a single fallback LLM model, used when the chosen model has no available
// node or the call errors (PRD 19 §7). The fallback may be an external model —
// in which case it spends the user's own provider key.
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { LifeBuoy, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/composables/useAuth'
import { usePlayground, type ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app', requireMember: true })

const { user, updateAccount } = useAuth()
const { listModels } = usePlayground()

const models = ref<ModelInfo[]>([])
const loading = ref(true)
const saving = ref(false)
const choice = ref('')

onMounted(async () => {
  choice.value = user.value?.fallback_model || ''
  try {
    models.value = (await listModels()).filter((m) => m.service_type === 'llm')
  } catch {
    /* leave empty; the picker shows "no models" */
  }
  loading.value = false
})

const current = computed(() => models.value.find((m) => m.id === choice.value))

const save = async (id: string) => {
  saving.value = true
  try {
    await updateAccount({ fallback_model: id })
    choice.value = id
    toast.success(id ? 'Fallback model set' : 'Fallback turned off')
  } catch {
    toast.error('Could not save fallback')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-2xl px-3 sm:px-6 py-6">
    <div class="mb-6">
      <h1 class="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        <LifeBuoy class="size-6" /> Fallback model
      </h1>
      <p class="mt-1 text-sm text-muted-foreground">
        When the model you pick has no available node — or the call errors or times out —
        inference.club retries once on this fallback. Pick an external model (OpenRouter / NVIDIA /
        Groq) and it'll keep working even when all your own nodes are offline.
        <span class="text-muted-foreground/80">Using an external fallback spends that provider's key.</span>
      </p>
    </div>

    <div v-if="loading" class="h-24 rounded-lg border bg-muted/30 animate-pulse" />

    <div v-else class="rounded-lg border p-4">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm font-medium">Current fallback</p>
          <p v-if="!choice" class="text-sm text-muted-foreground">None — requests fail if the chosen model is unavailable.</p>
          <p v-else class="flex items-center gap-2 text-sm">
            <span class="font-mono truncate">{{ current?.display_name || choice }}</span>
            <Badge v-if="current?.external" variant="secondary" class="shrink-0 text-[10px]">
              {{ current?.provider_label }}
            </Badge>
          </p>
        </div>
        <Button
          v-if="choice"
          variant="ghost"
          size="sm"
          class="shrink-0 text-muted-foreground hover:text-destructive"
          :disabled="saving"
          @click="save('')"
        >
          <X class="mr-1 size-3.5" /> Turn off
        </Button>
      </div>

      <div class="mt-3 border-t pt-3">
        <p class="mb-2 text-xs text-muted-foreground">Choose a fallback model</p>
        <ModelPicker
          :models="models"
          :model-value="choice"
          :loading="saving"
          @update:model-value="save"
        />
      </div>
    </div>
  </div>
</template>
