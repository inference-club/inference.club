<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { AudioLines, Clock, Dices, Download, Loader2, Music2, Square } from 'lucide-vue-next'
import { useMusicGeneration, type GeneratedSong } from '@/composables/useMusicGeneration'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { listMusicModels, generate } = useMusicGeneration()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// --- inputs ----------------------------------------------------------------
const prompt = ref('')
const lyrics = ref('')

// --- options ---------------------------------------------------------------
const duration = ref(30)
const steps = ref(8)
const guidance = ref(7)
const format = ref('mp3')
const randomizeSeed = ref(true)
const seed = ref(0)
const bpm = ref('')
const keyScale = ref('')

// --- run state -------------------------------------------------------------
const running = ref(false)
let controller: AbortController | null = null

interface ResultRow {
  id: string
  prompt: string
  song: GeneratedSong
  latencyMs: number
  model: string
  duration: number
}
const results = ref<ResultRow[]>([])

const uid = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.round(Math.random() * 1e9)}`

const canRun = computed(() => !!model.value && !!prompt.value.trim() && !running.value)

const num = (v: string) => {
  const n = Number(v)
  return v.trim() !== '' && !Number.isNaN(n) ? n : undefined
}

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const start = performance.now()
  const p = prompt.value.trim()
  try {
    const song = await generate(
      {
        model: model.value,
        prompt: p,
        lyrics: lyrics.value.trim() || undefined,
        audio_duration: duration.value,
        inference_steps: steps.value,
        guidance_scale: guidance.value,
        use_random_seed: randomizeSeed.value,
        seed: randomizeSeed.value ? undefined : seed.value,
        audio_format: format.value,
        bpm: num(bpm.value),
        key_scale: keyScale.value.trim() || undefined,
      },
      controller.signal,
    )
    results.value.unshift({
      id: uid(),
      prompt: p,
      song,
      latencyMs: Math.round(performance.now() - start),
      model: model.value,
      duration: duration.value,
    })
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Music generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

const download = (r: ResultRow) => {
  const a = document.createElement('a')
  a.href = r.song.url
  a.download = `song.${format.value === 'mp3' ? 'mp3' : format.value}`
  a.click()
}

const fmtDuration = (s: number) =>
  s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s}s`

onMounted(async () => {
  try {
    models.value = await listMusicModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
    } else {
      modelsError.value =
        'No music-generation models are available to you yet. Run an agent with a service of type: music (e.g. ACE-Step) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  results.value.forEach((r) => URL.revokeObjectURL(r.song.url))
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-4xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Music2 class="h-6 w-6" /> Music generation
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Describe a song — a style, mood, and instruments — add optional lyrics, and generate music.
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

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_18rem] gap-4 items-start">
      <!-- Composer -->
      <div class="min-w-0 space-y-3">
        <Card class="p-4 space-y-3">
          <div>
            <Label class="text-xs text-muted-foreground">Prompt</Label>
            <Textarea
              v-model="prompt"
              rows="3"
              placeholder="e.g. dreamy lo-fi hip-hop with mellow piano, soft vinyl crackle, 80 BPM"
              class="mt-1 resize-none text-sm"
            />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Lyrics (optional)</Label>
            <Textarea
              v-model="lyrics"
              rows="4"
              placeholder="[verse]&#10;Type lyrics here, or leave blank for an instrumental…"
              class="mt-1 resize-none text-sm font-mono"
            />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ prompt.length }} chars</span>
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component :is="running ? Loader2 : AudioLines" class="size-4" :class="running ? 'animate-spin' : ''" />
                Generate
              </Button>
            </div>
          </div>
        </Card>

        <!-- In-flight notice -->
        <Card v-if="running" class="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 class="size-4 animate-spin shrink-0" />
          Composing your song — this usually takes under a minute…
        </Card>

        <!-- Results -->
        <Card v-for="r in results" :key="r.id" class="p-4 space-y-3">
          <div class="flex items-center gap-2 flex-wrap text-[11px] text-muted-foreground">
            <Badge variant="outline" class="font-mono">{{ r.model }}</Badge>
            <span class="inline-flex items-center gap-1">
              <AudioLines class="size-3" /> {{ fmtDuration(r.duration) }}
            </span>
            <span class="inline-flex items-center gap-1"><Clock class="size-3" /> {{ r.latencyMs }} ms</span>
          </div>
          <p class="text-sm line-clamp-2">{{ r.prompt }}</p>
          <div class="flex items-center gap-2">
            <audio :src="r.song.url" controls class="h-10 flex-1" />
            <Button variant="ghost" size="icon" title="Download" @click="download(r)">
              <Download class="size-4" />
            </Button>
          </div>
        </Card>
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Duration: {{ fmtDuration(duration) }}</Label>
          <Input v-model.number="duration" type="range" min="10" max="240" step="5" class="mt-1 w-full" />
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Inference steps: {{ steps }}</Label>
          <Input v-model.number="steps" type="range" min="1" max="50" step="1" class="mt-1 w-full" />
          <p class="mt-1 text-[11px] text-muted-foreground">More steps = higher quality, slower.</p>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Guidance: {{ guidance }}</Label>
          <Input v-model.number="guidance" type="range" min="0" max="15" step="0.5" class="mt-1 w-full" />
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Format</Label>
          <Select v-model="format">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="mp3" class="text-sm">MP3</SelectItem>
              <SelectItem value="wav" class="text-sm">WAV</SelectItem>
              <SelectItem value="flac" class="text-sm">FLAC</SelectItem>
              <SelectItem value="opus" class="text-sm">Opus</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div>
            <Label class="text-xs text-muted-foreground">BPM</Label>
            <Input v-model="bpm" placeholder="auto" class="mt-1 h-8 text-sm" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Key</Label>
            <Input v-model="keyScale" placeholder="e.g. C Major" class="mt-1 h-8 text-sm" />
          </div>
        </div>

        <div class="border-t pt-4 space-y-2">
          <div class="flex items-center justify-between">
            <Label for="rand-seed" class="text-sm flex items-center gap-1.5">
              <Dices class="size-3.5" /> Randomize seed
            </Label>
            <Switch id="rand-seed" v-model="randomizeSeed" />
          </div>
          <div v-if="!randomizeSeed">
            <Label class="text-xs text-muted-foreground">Seed</Label>
            <Input v-model.number="seed" type="number" class="mt-1 h-8 text-sm" />
          </div>
        </div>

        <p class="text-[11px] text-muted-foreground border-t pt-3">
          Songs are generated on a provider's GPU and stored on inference.club.
        </p>
      </Card>
    </div>
  </div>
</template>
