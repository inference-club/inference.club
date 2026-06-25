<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { AudioLines, FileAudio, Library, Loader2, Mic, Square, Upload, X } from 'lucide-vue-next'
import { useTranscription } from '@/composables/useTranscription'
import { useAudioRecorder } from '@/composables/useAudioRecorder'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.transcription' })

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

// Bumped after each successful transcription so the recent-for-this-model strip
// refetches and flashes the one that just finished.
const refreshKey = ref(0)

const MAX_MB = 25

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

// Pick an existing speech generation (recent / starred / bookmarked / public
// search) as the source instead of uploading or recording.
const pickerOpen = ref(false)
const onPickClip = ({ blob, name }: { blob: Blob; name: string }) => {
  setPending(blob, name)
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
  const src = pending.value
  try {
    await transcribe(
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
    refreshKey.value++
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

useSubmitHotkey(run)

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
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
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
        <SelectTrigger class="w-full sm:w-[18rem] font-mono text-xs">
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
        <div class="flex flex-wrap items-center gap-2">
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
          <Button
            variant="outline"
            class="gap-2"
            data-testid="open-audio-picker"
            @click="pickerOpen = true"
          >
            <Library class="size-4" /> Generated clips
          </Button>
          <ElapsedTimer :running="running" class="text-xs text-muted-foreground" />
          <div class="ml-auto flex items-center gap-2">
            <GenerationSharingPicker />
            <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
              <Square class="size-4" /> Stop
            </Button>
            <Button :disabled="!canRun" class="gap-2" @click="run">
              <component :is="running ? Loader2 : AudioLines" class="size-4" :class="running ? 'animate-spin' : ''" />
              Transcribe
            </Button>
          </div>
        </div>

        <!-- Recent transcriptions for this model (the just-finished one flashes in) -->
        <RecentGenerations
          :model="model"
          type="STT"
          :refresh-key="refreshKey"
          title="Recent transcriptions"
          class="pt-2"
        />
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

    <AudioSourcePicker v-model:open="pickerOpen" @select="onPickClip" />
  </div>
</template>
