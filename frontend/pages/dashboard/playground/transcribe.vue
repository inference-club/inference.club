<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { AudioLines, Clock, FileAudio, Loader2, Mic, Square, Upload, X } from 'lucide-vue-next'
import { useTranscription, type TranscriptionResult } from '@/composables/useTranscription'
import { useAudioRecorder } from '@/composables/useAudioRecorder'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { listSttModels, transcribe } = useTranscription()
const recorder = useAudioRecorder()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

const selected = computed(() => models.value.find((m) => m.id === model.value))
const supportsTimestamps = computed(
  () => !!selected.value?.supported_features?.includes('timestamps'),
)

// --- audio source (uploaded or recorded) -----------------------------------
interface PendingAudio {
  blob: Blob
  name: string
  url: string // object URL for the <audio> preview
}
const pending = ref<PendingAudio | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

// --- options ---------------------------------------------------------------
const language = ref('')
const prompt = ref('')
const wantTimestamps = ref(false)

// --- run state -------------------------------------------------------------
const running = ref(false)
let controller: AbortController | null = null

interface ResultItem {
  id: string
  audioUrl: string
  filename: string
  result: TranscriptionResult
  latencyMs: number
  model: string
}
const results = ref<ResultItem[]>([])

const MAX_MB = 25
const uid = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.round(Math.random() * 1e9)}`

const setPending = (blob: Blob, name: string) => {
  if (blob.size > MAX_MB * 1024 * 1024) {
    toast.error(`Audio is too large (max ${MAX_MB} MB)`)
    return
  }
  if (pending.value) URL.revokeObjectURL(pending.value.url)
  pending.value = { blob, name, url: URL.createObjectURL(blob) }
}

const onFiles = (e: Event) => {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setPending(f, f.name)
  if (fileInput.value) fileInput.value.value = ''
}

const onDrop = (e: DragEvent) => {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  if (!f.type.startsWith('audio/') && !f.type.startsWith('video/')) {
    toast.error('Please drop an audio file')
    return
  }
  setPending(f, f.name)
}

const clearPending = () => {
  if (pending.value) URL.revokeObjectURL(pending.value.url)
  pending.value = null
}

// --- mic -------------------------------------------------------------------
const toggleMic = async () => {
  if (recorder.recording.value) {
    recorder.stop()
    return
  }
  try {
    const rec = await recorder.start()
    setPending(rec.blob, `recording.${rec.ext}`)
  } catch {
    toast.error('Microphone access was denied')
  }
}

// --- transcribe ------------------------------------------------------------
const canRun = computed(() => !!model.value && !!pending.value && !running.value)

const run = async () => {
  if (!canRun.value || !pending.value) return
  running.value = true
  controller = new AbortController()
  const start = performance.now()
  const src = pending.value
  try {
    const result = await transcribe(
      src.blob,
      src.name,
      {
        model: model.value,
        language: language.value.trim() || undefined,
        prompt: prompt.value.trim() || undefined,
        timestamps: wantTimestamps.value && supportsTimestamps.value,
      },
      controller.signal,
    )
    results.value.unshift({
      id: uid(),
      // Keep this object URL alive for replay in the result card; it's revoked
      // on unmount. Detach from `pending` so clearing the composer won't kill it.
      audioUrl: URL.createObjectURL(src.blob),
      filename: src.name,
      result,
      latencyMs: Math.round(performance.now() - start),
      model: model.value,
    })
    clearPending()
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Transcription failed')
  } finally {
    running.value = false
    controller = null
  }
}

const stop = () => controller?.abort()

const fmtSeconds = (s?: number | null) =>
  s == null ? null : s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`

onMounted(async () => {
  try {
    models.value = await listSttModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
    } else {
      modelsError.value =
        'No speech-to-text models are available to you yet. Run an STT agent (a service with type: stt) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  if (pending.value) URL.revokeObjectURL(pending.value.url)
  results.value.forEach((r) => URL.revokeObjectURL(r.audioUrl))
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-4xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <AudioLines class="h-6 w-6" /> Transcription
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Speech-to-text — upload or record audio and transcribe it with any STT model you can reach.
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

    <div v-if="selected" class="grid lg:grid-cols-[1fr_18rem] gap-4 items-start">
      <!-- Composer -->
      <div class="min-w-0 space-y-4">
        <!-- Drop zone -->
        <div
          class="rounded-2xl border-2 border-dashed transition-colors p-6 text-center"
          :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop"
        >
          <template v-if="pending">
            <div class="flex items-center gap-3">
              <FileAudio class="size-8 text-muted-foreground shrink-0" />
              <div class="min-w-0 flex-1 text-left">
                <p class="text-sm font-medium truncate">{{ pending.name }}</p>
                <audio :src="pending.url" controls class="w-full h-9 mt-1" />
              </div>
              <Button variant="ghost" size="icon" class="shrink-0" @click="clearPending">
                <X class="size-4" />
              </Button>
            </div>
          </template>
          <template v-else>
            <Upload class="size-8 mx-auto mb-2 text-muted-foreground opacity-60" />
            <p class="text-sm text-muted-foreground">
              Drag an audio file here, or
              <button class="text-primary underline" @click="fileInput?.click()">browse</button>
              <template v-if="recorder.supported.value"> / record below</template>
            </p>
            <p class="text-[11px] text-muted-foreground mt-1">
              wav, mp3, m4a, flac, ogg, webm · up to {{ MAX_MB }} MB
            </p>
          </template>
          <input
            ref="fileInput"
            type="file"
            accept="audio/*,video/mp4,video/webm"
            class="hidden"
            @change="onFiles"
          />
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-2">
          <Button
            v-if="recorder.supported.value"
            variant="outline"
            class="gap-2"
            :class="recorder.recording.value ? 'text-red-500 border-red-300' : ''"
            @click="toggleMic"
          >
            <component :is="recorder.recording.value ? Square : Mic" class="size-4" />
            {{ recorder.recording.value ? 'Stop' : 'Record' }}
          </Button>
          <div class="ml-auto flex items-center gap-2">
            <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
              <Square class="size-4" /> Stop
            </Button>
            <Button :disabled="!canRun" class="gap-2" @click="run">
              <component :is="running ? Loader2 : AudioLines" class="size-4" :class="running ? 'animate-spin' : ''" />
              Transcribe
            </Button>
          </div>
        </div>

        <!-- Results -->
        <div v-if="results.length" class="space-y-3 pt-2">
          <Card v-for="r in results" :key="r.id" class="p-4 space-y-3">
            <div class="flex items-center gap-2 flex-wrap text-[11px] text-muted-foreground">
              <Badge variant="outline" class="font-mono">{{ r.model }}</Badge>
              <span v-if="fmtSeconds(r.result.seconds)" class="inline-flex items-center gap-1">
                <AudioLines class="size-3" /> {{ fmtSeconds(r.result.seconds) }} audio
              </span>
              <span class="inline-flex items-center gap-1">
                <Clock class="size-3" /> {{ r.latencyMs }} ms
              </span>
            </div>
            <TranscriptView
              :text="r.result.text"
              :src="r.audioUrl"
              :words="r.result.words"
              :segments="r.result.segments"
              :language="r.result.language"
            />
          </Card>
        </div>
      </div>

      <!-- Options panel -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Language (optional)</Label>
          <Input v-model="language" placeholder="auto (e.g. en, es)" class="mt-1 h-8 text-sm" />
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Prompt / hint (optional)</Label>
          <Textarea v-model="prompt" rows="3" placeholder="Names, jargon, context…" class="mt-1 resize-none text-sm" />
        </div>
        <div class="flex items-center justify-between border-t pt-4">
          <div>
            <Label for="ts-toggle" class="text-sm">Word timestamps</Label>
            <p class="text-[11px] text-muted-foreground">
              {{ supportsTimestamps ? 'Interactive, click-to-seek transcript.' : 'Not supported by this model.' }}
            </p>
          </div>
          <Switch id="ts-toggle" v-model="wantTimestamps" :disabled="!supportsTimestamps" />
        </div>
      </Card>
    </div>
  </div>
</template>
