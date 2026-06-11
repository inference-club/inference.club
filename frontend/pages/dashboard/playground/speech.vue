<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { AudioLines, Loader2, Mic2, Square } from 'lucide-vue-next'
import { useTextToSpeech } from '@/composables/useTextToSpeech'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { listTtsModels, listVoices, synthesize } = useTextToSpeech()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

const text = ref('')
const voices = ref<string[]>([])
const voice = ref('')
const loadingVoices = ref(false)
const format = ref('wav')

const running = ref(false)
let controller: AbortController | null = null

// Bumped after each successful synthesis so the recent-for-this-model strip
// refetches and flashes the clip that just finished.
const refreshKey = ref(0)

const canRun = computed(() => !!model.value && !!text.value.trim() && !running.value)

const loadVoices = async () => {
  if (!model.value) return
  loadingVoices.value = true
  try {
    voices.value = await listVoices(model.value)
    // Keep current selection if still valid, else default to the first voice.
    if (!voices.value.includes(voice.value)) voice.value = voices.value[0] || ''
  } finally {
    loadingVoices.value = false
  }
}

watch(model, loadVoices)

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const t = text.value.trim()
  try {
    const audio = await synthesize(
      { model: model.value, input: t, voice: voice.value || undefined, response_format: format.value },
      controller.signal,
    )
    // Play it back from its persisted TTS request (in the recent strip), not the
    // transient blob — so release the object URL the client made.
    URL.revokeObjectURL(audio.url)
    refreshKey.value++
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Speech synthesis failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

onMounted(async () => {
  try {
    models.value = await listTtsModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
      const p = usePlaygroundPrefill().take('TTS')
      if (p && typeof p.model === 'string' && models.value.some((m) => m.id === p.model)) {
        model.value = p.model
      }
      await loadVoices()
      if (p) {
        if (typeof p.input === 'string') text.value = p.input
        if (typeof p.response_format === 'string') format.value = p.response_format
        if (typeof p.voice === 'string' && voices.value.includes(p.voice)) voice.value = p.voice
      }
    } else {
      modelsError.value =
        'No text-to-speech models are available to you yet. Run a TTS agent (a service with type: tts) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Mic2 class="h-6 w-6" /> Text to speech
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Type text, pick a voice, and synthesize natural speech.
        </p>
      </div>
      <Select v-model="model" :disabled="loadingModels || !models.length">
        <SelectTrigger class="w-[18rem] font-mono text-xs">
          <SelectValue :placeholder="loadingModels ? 'Loading models…' : 'Select a model'" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="m in models" :key="m.id" :value="m.id" class="font-mono text-xs">
            {{ m.id }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-muted text-muted-foreground rounded text-sm">
      {{ modelsError }}
    </div>

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_16rem] gap-4 items-start">
      <!-- Composer -->
      <div class="space-y-3">
        <Card class="p-4 space-y-3">
          <Textarea
            v-model="text"
            rows="5"
            placeholder="Type something to say aloud…"
            class="resize-none text-sm"
          />
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ text.length }} characters</span>
            <ElapsedTimer :running="running" class="text-xs text-muted-foreground" />
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component :is="running ? Loader2 : AudioLines" class="size-4" :class="running ? 'animate-spin' : ''" />
                Synthesize
              </Button>
            </div>
          </div>
        </Card>

        <!-- Recent speech for this model (the just-finished one flashes in) -->
        <RecentGenerations :model="model" type="TTS" :refresh-key="refreshKey" title="Recent speech" />
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Voice</Label>
          <Select v-model="voice" :disabled="loadingVoices || !voices.length">
            <SelectTrigger class="mt-1 h-8 text-sm">
              <SelectValue :placeholder="loadingVoices ? 'Loading…' : (voices.length ? 'Select a voice' : 'No voices')" />
            </SelectTrigger>
            <SelectContent class="max-h-72">
              <SelectItem v-for="v in voices" :key="v" :value="v" class="text-xs">{{ v }}</SelectItem>
            </SelectContent>
          </Select>
          <p class="mt-1 text-[11px] text-muted-foreground">{{ voices.length }} voices available.</p>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Format</Label>
          <Select v-model="format">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="wav" class="text-sm">WAV</SelectItem>
              <SelectItem value="opus" class="text-sm">Opus</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>
    </div>
  </div>
</template>
