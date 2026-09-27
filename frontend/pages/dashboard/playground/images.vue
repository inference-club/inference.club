<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ChevronDown, Dices, Image as ImageIcon, Images, Lightbulb, Sparkles, Square, Upload, X } from 'lucide-vue-next'
import { useImageGeneration } from '@/composables/useImageGeneration'
import { SUGGESTED_IMAGE_PROMPTS } from '@/utils/imagePrompts'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.images' })

const { listImageModels, generate, edit } = useImageGeneration()

// Suggested prompts — collapsible; clicking one fills the prompt box.
const showSuggestions = ref(false)
const useSuggestion = (text: string) => {
  prompt.value = text
}

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

const prompt = ref('')
const n = ref(1)

// Per-model feature flags (from `supported_features` on /v1/models — the
// provider declares them per model, see docs/providers/kubernetes-agent).
// They decide which controls are shown; a model without a flag never sees
// the field, so plain providers keep getting plain requests.
const current = computed(() => models.value.find((m) => m.id === model.value))
const has = (f: string) => current.value?.supported_features?.includes(f) ?? false
const canEdit = computed(() => has('image-edit') || (current.value?.input_modalities ?? []).includes('image'))
const maxImages = computed(() => (has('multi-reference') ? (model.value.startsWith('qwen-image') ? 10 : 8) : has('image-edit') ? 1 : 0))
const hasSeed = computed(() => has('seed'))
const hasSteps = computed(() => has('steps'))
const hasNegative = computed(() => has('negative-prompt'))
const hasTransparent = computed(() => has('transparent-background'))
const hasCustomSize = computed(() => has('custom-size'))
const hasAdvanced = computed(() => hasSeed.value || hasSteps.value || hasNegative.value || hasTransparent.value)

// Model-specific knobs. Empty/undefined means "model default" and is not sent.
const seed = ref<number | null>(null)
const randomSeed = () => { seed.value = Math.floor(Math.random() * 2_147_483_647) }
const steps = ref<number | null>(null)
const negativePrompt = ref('')
const guidance = ref(4)
const transparent = ref(false)
const showAdvanced = ref(false)

// Aspect-ratio presets — each maps to a concrete WxH the API receives via the
// `size` param. Sizes are ~1MP, SDXL-friendly dimensions (multiples of 64).
interface AspectPreset { label: string; ratio: string; w: number; h: number }
const ASPECT_PRESETS: AspectPreset[] = [
  { label: 'Square', ratio: '1:1', w: 1024, h: 1024 },
  { label: 'Landscape', ratio: '3:2', w: 1216, h: 832 },
  { label: 'Portrait', ratio: '2:3', w: 832, h: 1216 },
  { label: 'Widescreen', ratio: '16:9', w: 1344, h: 768 },
  { label: 'Tall', ratio: '9:16', w: 768, h: 1344 },
  { label: 'Landscape', ratio: '4:3', w: 1152, h: 896 },
  { label: 'Portrait', ratio: '3:4', w: 896, h: 1152 },
]
// Native-2K presets for models that advertise `custom-size` (Qwen-Image 2.1's
// seven official ratios). Slower — a 2K render is ~4× the pixels of 1 MP.
const LARGE_PRESETS: AspectPreset[] = [
  { label: '2K Square', ratio: '1:1', w: 2048, h: 2048 },
  { label: '2K Landscape', ratio: '4:3', w: 2400, h: 1792 },
  { label: '2K Portrait', ratio: '3:4', w: 1792, h: 2400 },
  { label: '2K Landscape', ratio: '3:2', w: 2528, h: 1696 },
  { label: '2K Portrait', ratio: '2:3', w: 1696, h: 2528 },
  { label: '2K Widescreen', ratio: '16:9', w: 2752, h: 1536 },
  { label: '2K Tall', ratio: '9:16', w: 1536, h: 2752 },
]
const presets = computed(() => (hasCustomSize.value ? [...ASPECT_PRESETS, ...LARGE_PRESETS] : ASPECT_PRESETS))
const size = ref(`${ASPECT_PRESETS[0].w}x${ASPECT_PRESETS[0].h}`)
// Custom WxH (multiples of 32, ≤ 2048 per side on Qwen-Image 2.1) — only
// offered when the model declares `custom-size`.
const customSize = ref(false)
const customW = ref(1024)
const customH = ref(1024)
const MAX_SIDE = 2048
const snap = (v: number) => Math.max(256, Math.min(MAX_SIDE, Math.round(v / 32) * 32))
const effectiveSize = computed(() =>
  customSize.value && hasCustomSize.value ? `${snap(customW.value)}x${snap(customH.value)}` : size.value,
)
const currentPreset = computed<AspectPreset>(() => {
  if (customSize.value && hasCustomSize.value) {
    return { label: 'Custom', ratio: '', w: snap(customW.value), h: snap(customH.value) }
  }
  return presets.value.find((p) => `${p.w}x${p.h}` === size.value) ?? ASPECT_PRESETS[0]
})

// Optional source images → switches to the edit endpoint. One source is a
// classic single-image edit; several are reference images the model fuses
// together (FLUX.2 Klein up to 8, Qwen-Image 2.1 up to 10 — refer to them as
// "image 1", "image 2", … in the prompt).
interface SourceImage { blob: Blob; name: string; url: string }
const sources = ref<SourceImage[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const MAX_MB = 25
const MAX_IMAGES = computed(() => maxImages.value)

const running = ref(false)
let controller: AbortController | null = null

// Bumped after each successful generation so the recent-for-this-model strip
// refetches and flashes the image that just finished.
const refreshKey = ref(0)

const addSource = (blob: Blob, name: string) => {
  if (blob.size > MAX_MB * 1024 * 1024) {
    toast.error(`Image too large (max ${MAX_MB} MB)`)
    return
  }
  if (sources.value.length >= MAX_IMAGES.value) {
    toast.error(`Up to ${MAX_IMAGES.value} reference images`)
    return
  }
  sources.value.push({ blob, name, url: URL.createObjectURL(blob) })
}
const onFiles = (e: Event) => {
  const files = (e.target as HTMLInputElement).files
  if (files) for (const f of Array.from(files)) addSource(f, f.name)
  if (fileInput.value) fileInput.value.value = ''
}
const onDrop = (e: DragEvent) => {
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (!files?.length) return
  for (const f of Array.from(files)) {
    if (!f.type.startsWith('image/')) { toast.error('Please drop image files'); continue }
    addSource(f, f.name)
  }
}
const removeSource = (i: number) => {
  const [removed] = sources.value.splice(i, 1)
  if (removed) URL.revokeObjectURL(removed.url)
}
const clearSources = () => {
  for (const s of sources.value) URL.revokeObjectURL(s.url)
  sources.value = []
}
const pickerOpen = ref(false)
const onPickImage = ({ blob, name }: { blob: Blob; name: string }) => addSource(blob, name)

const canRun = computed(() => !!model.value && !!prompt.value.trim() && !running.value)

// Everything the request carries besides the prompt. Feature-gated: a knob
// the current model doesn't advertise is left out even if the field holds a
// value from a previous model.
const requestOptions = () => ({
  model: model.value,
  prompt: prompt.value.trim(),
  n: n.value,
  size: effectiveSize.value,
  ...(hasSeed.value && seed.value !== null ? { seed: seed.value } : {}),
  ...(hasSteps.value && steps.value ? { steps: steps.value } : {}),
  ...(hasNegative.value && negativePrompt.value.trim()
    ? { negative_prompt: negativePrompt.value.trim(), guidance: guidance.value }
    : {}),
  ...(hasTransparent.value && transparent.value ? { background: 'transparent' as const } : {}),
})

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const srcs = sources.value
  try {
    if (srcs.length) {
      await edit(srcs.map((s) => ({ blob: s.blob, name: s.name })), requestOptions(), controller.signal)
    } else {
      await generate(requestOptions(), controller.signal)
    }
    refreshKey.value++
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

// ⌘/Ctrl+Enter generates (or edits) — so you can tweak options then fire
// without reaching for the button.
useSubmitHotkey(run)

// Queue N copies as async jobs (text-to-image only — edits need an upload, so
// the dropdown is hidden when source images are attached).
const { queue } = useQueueGenerations()
const onQueue = (count: number) => {
  if (!model.value || !prompt.value.trim()) return
  queue('/v1/images/generations', requestOptions(), count, 'image')
}

onMounted(async () => {
  try {
    models.value = await listImageModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
      const p = usePlaygroundPrefill().take('IMAGE')
      if (p) {
        if (typeof p.prompt === 'string') prompt.value = p.prompt
        if (typeof p.n === 'number') n.value = p.n
        if (typeof p.size === 'string') size.value = p.size
        if (typeof p.model === 'string' && models.value.some((m) => m.id === p.model)) model.value = p.model
      }
    } else {
      modelsError.value =
        'No image models are available to you yet. Run an image agent (a service with type: image) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  for (const s of sources.value) URL.revokeObjectURL(s.url)
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <ImageIcon class="h-6 w-6" /> Image generation
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Text-to-image — describe an image, or attach one to edit it. Add several
          reference images and the model fuses them into one.
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

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_16rem] gap-4 items-start">
      <!-- Composer -->
      <div class="space-y-3">
        <Card class="p-4 space-y-3">
          <Textarea
            v-model="prompt"
            rows="3"
            placeholder="A watercolor fox in a misty forest at dawn…  (⌘/Ctrl+Enter to generate)"
            class="resize-none text-sm"
          />

          <!-- Suggested prompts (collapsible) -->
          <div class="rounded-lg border bg-muted/30">
            <button
              type="button"
              class="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
              @click="showSuggestions = !showSuggestions"
            >
              <Lightbulb class="size-3.5" />
              Need inspiration? {{ SUGGESTED_IMAGE_PROMPTS.length }} suggested prompts
              <ChevronDown
                class="ml-auto size-4 transition-transform"
                :class="showSuggestions ? 'rotate-180' : ''"
              />
            </button>
            <div v-if="showSuggestions" class="max-h-60 overflow-y-auto px-3 pb-3">
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="(p, i) in SUGGESTED_IMAGE_PROMPTS"
                  :key="i"
                  type="button"
                  class="rounded-full border bg-background px-2.5 py-1 text-left text-[11px] text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
                  :title="p"
                  @click="useSuggestion(p)"
                >
                  {{ p.length > 60 ? p.slice(0, 60) + '…' : p }}
                </button>
              </div>
            </div>
          </div>
          <!-- Optional source image(s) — only for models that take references -->
          <div
            v-if="canEdit"
            class="rounded-xl border border-dashed transition-colors p-3 text-center text-sm"
            :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <!-- Thumbnails of the chosen sources -->
            <div v-if="sources.length" class="flex flex-wrap gap-2">
              <div
                v-for="(s, i) in sources"
                :key="i"
                class="group relative size-16 shrink-0 overflow-hidden rounded border"
              >
                <img :src="s.url" :title="s.name" class="size-full object-cover" />
                <button
                  type="button"
                  class="absolute right-0.5 top-0.5 rounded-full bg-black/60 p-0.5 text-white opacity-0 transition-opacity group-hover:opacity-100"
                  :aria-label="`Remove ${s.name}`"
                  @click="removeSource(i)"
                >
                  <X class="size-3" />
                </button>
              </div>
              <button
                v-if="sources.length < MAX_IMAGES"
                type="button"
                class="flex size-16 shrink-0 flex-col items-center justify-center gap-0.5 rounded border border-dashed text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
                @click="fileInput?.click()"
              >
                <Upload class="size-4" />
                <span class="text-[10px]">Add</span>
              </button>
            </div>
            <div v-else class="text-muted-foreground">
              <Upload class="size-4 inline mr-1 opacity-60" />
              Drag image(s) to <em>edit</em> or combine, or
              <button class="text-primary underline" @click="fileInput?.click()">browse</button>
              <span class="text-[11px]"> (optional)</span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFiles" />
          </div>
          <div v-if="canEdit" class="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              class="gap-2"
              :disabled="sources.length >= MAX_IMAGES"
              @click="pickerOpen = true"
            >
              <Images class="size-4" /> Use an existing image
            </Button>
            <button
              v-if="sources.length"
              type="button"
              class="text-xs text-muted-foreground hover:text-foreground"
              @click="clearSources"
            >
              Clear all
            </button>
            <span v-if="sources.length > 1" class="text-xs text-muted-foreground">
              {{ sources.length }} of {{ MAX_IMAGES }} reference images — say "image 1", "image 2"… in the prompt
            </span>
          </div>

          <div class="flex flex-wrap items-center gap-x-2 gap-y-2">
            <span class="text-xs text-muted-foreground">{{ sources.length ? 'Edit mode' : 'Generate mode' }}</span>
            <ElapsedTimer :running="running" class="text-xs text-muted-foreground" />
            <div class="ml-auto flex items-center gap-2">
              <GenerationSharingPicker compact />
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <GenerateButton
                :disabled="!canRun"
                :queue-disabled="!model || !prompt.trim()"
                :running="running"
                :icon="Sparkles"
                :label="sources.length ? 'Edit' : 'Generate'"
                :queueable="!sources.length"
                noun="image"
                @generate="run"
                @queue="onQueue"
              />
            </div>
          </div>
        </Card>

        <!-- Recent images for this model (the just-finished one flashes in) -->
        <RecentGenerations :model="model" type="IMAGE" :refresh-key="refreshKey" title="Recent images" />
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>
        <div>
          <div class="flex items-center justify-between">
            <Label class="text-xs text-muted-foreground">{{ customSize && hasCustomSize ? 'Size' : 'Aspect ratio' }}</Label>
            <button
              v-if="hasCustomSize"
              type="button"
              class="text-[11px] text-primary underline-offset-2 hover:underline"
              @click="customSize = !customSize"
            >
              {{ customSize ? 'Use a preset' : 'Custom size' }}
            </button>
          </div>
          <div v-if="customSize && hasCustomSize" class="mt-1 flex items-center gap-1">
            <Input id="img-w" v-model.number="customW" type="number" :min="256" :max="MAX_SIDE" step="32" class="h-8 text-sm tabular-nums" aria-label="Width" />
            <span class="text-xs text-muted-foreground">×</span>
            <Input id="img-h" v-model.number="customH" type="number" :min="256" :max="MAX_SIDE" step="32" class="h-8 text-sm tabular-nums" aria-label="Height" />
          </div>
          <Select v-else v-model="size">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="p in presets"
                :key="`${p.w}x${p.h}`"
                :value="`${p.w}x${p.h}`"
                class="text-sm"
              >
                {{ p.label }} · {{ p.ratio }}
              </SelectItem>
            </SelectContent>
          </Select>

          <!-- Live shape preview. An SVG with preserveAspectRatio letterboxes
               the WxH viewBox to fit the box (true object-fit: contain), so the
               drawn rect always carries the real aspect ratio regardless of the
               container's own shape — a plain div with max-w/max-h + aspectRatio
               can't (clamping one axis distorts the other). -->
          <div class="mt-2 flex h-32 items-center justify-center rounded-lg border bg-muted/30 p-3">
            <svg
              :viewBox="`0 0 ${currentPreset.w} ${currentPreset.h}`"
              preserveAspectRatio="xMidYMid meet"
              class="h-full w-full overflow-visible"
            >
              <rect
                x="0"
                y="0"
                :width="currentPreset.w"
                :height="currentPreset.h"
                :rx="Math.min(currentPreset.w, currentPreset.h) * 0.05"
                class="fill-primary/10 stroke-primary/50"
                stroke-width="2"
                vector-effect="non-scaling-stroke"
              />
            </svg>
          </div>
          <p class="mt-1 text-center text-[11px] text-muted-foreground tabular-nums">
            {{ currentPreset.w }} × {{ currentPreset.h }}
          </p>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Number of images</Label>
          <Input v-model.number="n" type="number" min="1" max="4" class="mt-1 h-8 text-sm" />
        </div>

        <!-- Model-specific knobs, shown only when the model advertises them -->
        <div v-if="hasTransparent" class="flex items-center justify-between gap-2">
          <Label for="img-transparent" class="text-xs text-muted-foreground">Transparent background</Label>
          <Switch id="img-transparent" v-model="transparent" />
        </div>
        <div v-if="hasAdvanced" class="rounded-lg border">
          <button
            type="button"
            class="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
            @click="showAdvanced = !showAdvanced"
          >
            Advanced
            <ChevronDown class="ml-auto size-4 transition-transform" :class="showAdvanced ? 'rotate-180' : ''" />
          </button>
          <div v-if="showAdvanced" class="space-y-3 px-3 pb-3">
            <div v-if="hasSeed">
              <Label for="img-seed" class="text-xs text-muted-foreground">Seed</Label>
              <div class="mt-1 flex items-center gap-1">
                <Input id="img-seed" v-model.number="seed" type="number" min="0" placeholder="random" class="h-8 text-sm tabular-nums" />
                <Button variant="outline" size="icon" class="size-8 shrink-0" title="Random seed" @click="randomSeed">
                  <Dices class="size-4" />
                </Button>
                <Button v-if="seed !== null" variant="ghost" size="icon" class="size-8 shrink-0" title="Clear (random each run)" @click="seed = null">
                  <X class="size-4" />
                </Button>
              </div>
            </div>
            <div v-if="hasSteps">
              <Label for="img-steps" class="text-xs text-muted-foreground">Steps</Label>
              <Input id="img-steps" v-model.number="steps" type="number" min="1" max="100" placeholder="model default (40)" class="mt-1 h-8 text-sm tabular-nums" />
            </div>
            <div v-if="hasNegative">
              <Label for="img-negative" class="text-xs text-muted-foreground">Negative prompt</Label>
              <Textarea id="img-negative" v-model="negativePrompt" rows="2" placeholder="text, watermark, blurry…" class="mt-1 resize-none text-sm" />
              <div v-if="negativePrompt.trim()" class="mt-2">
                <Label for="img-guidance" class="text-xs text-muted-foreground">Guidance scale · {{ guidance }}</Label>
                <input id="img-guidance" v-model.number="guidance" type="range" min="1" max="10" step="0.5" class="mt-1 w-full">
                <p class="text-[11px] text-muted-foreground">Doubles the work per step. Qwen-Image 2.1 is tuned for no guidance; 4 is a good starting point.</p>
              </div>
            </div>
          </div>
        </div>
        <p class="text-[11px] text-muted-foreground">
          Images are generated on a provider's GPU and stored on inference.club.
        </p>
      </Card>
    </div>

    <ImageSourcePicker v-model:open="pickerOpen" @select="onPickImage" />
  </div>
</template>
