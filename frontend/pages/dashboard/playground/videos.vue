<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  ChevronDown, Clapperboard, Dices, Film, Images, Loader2, Sparkles, Square, Upload, X,
} from 'lucide-vue-next'
import { useVideoGeneration } from '@/composables/useVideoGeneration'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { listVideoModels, generate } = useVideoGeneration()
const prefill = usePlaygroundPrefill()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// --- inputs ----------------------------------------------------------------
const prompt = ref('')
const negativePrompt = ref('')
const showNegative = ref(false)

// Optional first-frame image (image-to-video). Omit for pure text-to-video.
interface SourceImage { blob: Blob; name: string; url: string }
const source = ref<SourceImage | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const MAX_MB = 25
const imageStrength = ref(1)

const setSource = (blob: Blob, name: string) => {
  if (blob.size > MAX_MB * 1024 * 1024) {
    toast.error(`That image is over ${MAX_MB}MB — pick a smaller one.`)
    return
  }
  if (source.value) URL.revokeObjectURL(source.value.url)
  source.value = { blob, name, url: URL.createObjectURL(blob) }
}
const onFiles = (e: Event) => {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setSource(f, f.name)
  if (fileInput.value) fileInput.value.value = ''
}
const onDrop = (e: DragEvent) => {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  if (!f.type.startsWith('image/')) return toast.error('Drop an image file.')
  setSource(f, f.name)
}
const clearSource = () => {
  if (source.value) URL.revokeObjectURL(source.value.url)
  source.value = null
}
const pickerOpen = ref(false)
const onPickImage = ({ blob, name }: { blob: Blob; name: string }) => setSource(blob, name)

// --- options ---------------------------------------------------------------
const RESOLUTIONS = [
  { value: '1280x704', label: 'Landscape · 1280×704' },
  { value: '704x1280', label: 'Portrait · 704×1280' },
  { value: '768x768', label: 'Square · 768×768' },
  { value: '1152x640', label: 'Wide · 1152×640' },
]
const resolution = ref('1280x704')
const duration = ref(5)
const fps = ref('24')
const steps = ref(30)
const guidance = ref(3)
const enhancePrompt = ref(false)
const randomizeSeed = ref(true)
const seed = ref(0)
const showAdvanced = ref(false)
const numFrames = ref('') // optional override; blank = derive from duration × fps

// --- run state -------------------------------------------------------------
const running = ref(false)
let controller: AbortController | null = null
const refreshKey = ref(0)

const canRun = computed(() => !!model.value && !!prompt.value.trim() && !running.value)

const num = (v: string) => {
  const n = Number(v)
  return v.trim() !== '' && !Number.isNaN(n) ? n : undefined
}

const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result))
    fr.onerror = () => reject(new Error('Could not read the image'))
    fr.readAsDataURL(blob)
  })

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const [w, h] = resolution.value.split('x').map((n) => Number(n))
  try {
    const image = source.value ? await blobToDataUrl(source.value.blob) : undefined
    const video = await generate(
      {
        model: model.value,
        prompt: prompt.value.trim(),
        negative_prompt: negativePrompt.value.trim() || undefined,
        image,
        image_strength: image ? imageStrength.value : undefined,
        duration: duration.value,
        num_frames: num(numFrames.value),
        fps: Number(fps.value),
        width: w,
        height: h,
        num_inference_steps: steps.value,
        guidance_scale: guidance.value,
        enhance_prompt: enhancePrompt.value,
        use_random_seed: randomizeSeed.value,
        seed: randomizeSeed.value ? undefined : seed.value,
      },
      controller.signal,
    )
    // We play it back from the persisted VIDEO request (recent strip), not the
    // transient blob — so release the object URL the client made.
    URL.revokeObjectURL(video.url)
    refreshKey.value++
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Video generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

// Populate the form from a "Reproduce in playground" handoff, if any. (The
// first-frame image isn't re-attached — text + controls only.)
const applyPrefill = () => {
  const p = prefill.take('VIDEO')
  if (!p) return
  if (typeof p.prompt === 'string') prompt.value = p.prompt
  if (typeof p.negative_prompt === 'string' && p.negative_prompt) {
    negativePrompt.value = p.negative_prompt
    showNegative.value = true
  }
  if (typeof p.duration === 'number') duration.value = p.duration
  if (typeof p.fps === 'number') fps.value = String(p.fps)
  if (typeof p.num_inference_steps === 'number') steps.value = p.num_inference_steps
  if (typeof p.guidance_scale === 'number') guidance.value = p.guidance_scale
  if (typeof p.enhance_prompt === 'boolean') enhancePrompt.value = p.enhance_prompt
  if (typeof p.width === 'number' && typeof p.height === 'number') {
    const r = `${p.width}x${p.height}`
    if (RESOLUTIONS.some((x) => x.value === r)) resolution.value = r
  }
  if (typeof p.seed === 'number') {
    seed.value = p.seed
    randomizeSeed.value = false
  }
  if (typeof p.model === 'string' && models.value.some((m) => m.id === p.model)) model.value = p.model
}

onMounted(async () => {
  try {
    models.value = await listVideoModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
      applyPrefill()
    } else {
      modelsError.value =
        'No video-generation models are available to you yet. Run an agent with a service of type: video (e.g. LTX-2) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  controller?.abort()
  if (source.value) URL.revokeObjectURL(source.value.url)
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-5xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Clapperboard class="h-6 w-6" /> Video generation
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Describe a scene — or drop in a first frame — and generate a short video.
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
              placeholder="e.g. a red fox trots across a snow-covered meadow at dawn, camera slowly tracking alongside, soft golden light"
              class="mt-1 resize-none text-sm"
            />
          </div>

          <!-- Negative prompt (optional, collapsible) -->
          <div>
            <button
              type="button"
              class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              @click="showNegative = !showNegative"
            >
              <ChevronDown class="size-3 transition-transform" :class="showNegative ? 'rotate-0' : '-rotate-90'" />
              Negative prompt
            </button>
            <Textarea
              v-if="showNegative"
              v-model="negativePrompt"
              rows="2"
              placeholder="What to avoid — leave blank for the model's default"
              class="mt-1 resize-none text-sm"
            />
          </div>

          <!-- First-frame image (optional) -->
          <div
            class="rounded-xl border border-dashed transition-colors p-3 text-center text-sm"
            :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div v-if="source" class="flex items-center gap-3">
              <img :src="source.url" class="size-16 rounded object-cover border" />
              <span class="text-xs text-muted-foreground flex-1 text-left truncate">
                First frame: <strong>{{ source.name }}</strong>
              </span>
              <Button variant="ghost" size="icon" @click="clearSource"><X class="size-4" /></Button>
            </div>
            <div v-else class="text-muted-foreground py-1">
              <Upload class="size-5 inline mr-1 opacity-60" />
              Drop a first-frame image (optional, for image-to-video), or
              <button class="text-primary underline" @click="fileInput?.click()">browse</button>
            </div>
            <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFiles" />
          </div>
          <div class="flex items-center gap-2">
            <Button variant="outline" size="sm" class="gap-2" @click="pickerOpen = true">
              <Images class="size-4" /> Use an existing image
            </Button>
            <div v-if="source" class="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
              <Label class="text-xs text-muted-foreground whitespace-nowrap">Image strength {{ imageStrength.toFixed(2) }}</Label>
              <Input v-model.number="imageStrength" type="range" min="0" max="1" step="0.05" class="w-28" />
            </div>
          </div>

          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ prompt.length }} chars</span>
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component :is="running ? Loader2 : Film" class="size-4" :class="running ? 'animate-spin' : ''" />
                Generate
              </Button>
            </div>
          </div>
        </Card>

        <!-- In-flight notice (video generation is slow) -->
        <Card v-if="running" class="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 class="size-4 animate-spin shrink-0" />
          <span class="flex-1">Rendering your video — this can take a couple of minutes…</span>
          <ElapsedTimer :running="running" class="shrink-0 font-medium text-foreground" />
        </Card>

        <!-- Recent videos for this model (the just-finished one flashes in) -->
        <RecentGenerations :model="model" type="VIDEO" :refresh-key="refreshKey" title="Recent videos" />
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>

        <div>
          <Label class="text-xs text-muted-foreground">Resolution</Label>
          <Select v-model="resolution">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="r in RESOLUTIONS" :key="r.value" :value="r.value" class="text-sm">
                {{ r.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Duration: {{ duration }}s</Label>
          <Input v-model.number="duration" type="range" min="1" max="10" step="1" class="mt-1 w-full" />
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Frame rate</Label>
          <Select v-model="fps">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="16" class="text-sm">16 fps</SelectItem>
              <SelectItem value="24" class="text-sm">24 fps</SelectItem>
              <SelectItem value="30" class="text-sm">30 fps</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Steps: {{ steps }}</Label>
          <Input v-model.number="steps" type="range" min="1" max="50" step="1" class="mt-1 w-full" />
          <p class="mt-1 text-[11px] text-muted-foreground">Some distilled pipelines use a fixed step count and ignore this.</p>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Guidance: {{ guidance }}</Label>
          <Input v-model.number="guidance" type="range" min="0" max="15" step="0.5" class="mt-1 w-full" />
        </div>

        <div class="flex items-center justify-between">
          <Label for="enhance" class="text-sm flex items-center gap-1.5">
            <Sparkles class="size-3.5" /> Enhance prompt
          </Label>
          <Switch id="enhance" v-model="enhancePrompt" />
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
            <Input v-model.number="seed" type="number" class="mt-1 h-8 text-sm tabular-nums" />
          </div>
        </div>

        <!-- Advanced: exact frame-count override -->
        <div class="border-t pt-3">
          <button
            type="button"
            class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            @click="showAdvanced = !showAdvanced"
          >
            <ChevronDown class="size-3 transition-transform" :class="showAdvanced ? 'rotate-0' : '-rotate-90'" />
            Advanced
          </button>
          <div v-if="showAdvanced" class="mt-2">
            <Label class="text-xs text-muted-foreground">Frames (override)</Label>
            <Input v-model="numFrames" placeholder="auto (duration × fps)" class="mt-1 h-8 text-sm" />
            <p class="mt-1 text-[11px] text-muted-foreground">Snapped to 8k+1. Overrides duration when set.</p>
          </div>
        </div>

        <p class="text-[11px] text-muted-foreground border-t pt-3">
          Videos are generated on a provider's GPU and stored on inference.club.
        </p>
      </Card>
    </div>

    <ImageSourcePicker v-model:open="pickerOpen" @select="onPickImage" />
  </div>
</template>
