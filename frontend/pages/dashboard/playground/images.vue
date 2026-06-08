<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ChevronDown, Image as ImageIcon, Lightbulb, Loader2, Sparkles, Square, Upload, X } from 'lucide-vue-next'
import { useImageGeneration } from '@/composables/useImageGeneration'
import { SUGGESTED_IMAGE_PROMPTS } from '@/utils/imagePrompts'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

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
const size = ref(`${ASPECT_PRESETS[0].w}x${ASPECT_PRESETS[0].h}`)
const currentPreset = computed(
  () => ASPECT_PRESETS.find((p) => `${p.w}x${p.h}` === size.value) ?? ASPECT_PRESETS[0],
)

// Optional source image → switches to the edit endpoint.
interface SourceImage { blob: Blob; name: string; url: string }
const source = ref<SourceImage | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const MAX_MB = 25

const running = ref(false)
let controller: AbortController | null = null

// Bumped after each successful generation so the recent-for-this-model strip
// refetches and flashes the image that just finished.
const refreshKey = ref(0)

const setSource = (blob: Blob, name: string) => {
  if (blob.size > MAX_MB * 1024 * 1024) {
    toast.error(`Image too large (max ${MAX_MB} MB)`)
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
  if (!f.type.startsWith('image/')) return toast.error('Please drop an image file')
  setSource(f, f.name)
}
const clearSource = () => {
  if (source.value) URL.revokeObjectURL(source.value.url)
  source.value = null
}

const canRun = computed(() => !!model.value && !!prompt.value.trim() && !running.value)

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const p = prompt.value.trim()
  const src = source.value
  try {
    if (src) {
      await edit(src.blob, src.name, { model: model.value, prompt: p, n: n.value, size: size.value }, controller.signal)
    } else {
      await generate({ model: model.value, prompt: p, n: n.value, size: size.value }, controller.signal)
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
const onPromptKeydown = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault()
    run()
  }
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
  if (source.value) URL.revokeObjectURL(source.value.url)
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-5xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <ImageIcon class="h-6 w-6" /> Image generation
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Text-to-image — describe an image, or attach one to edit it with your prompt.
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
            v-model="prompt"
            rows="3"
            placeholder="A watercolor fox in a misty forest at dawn…  (⌘/Ctrl+Enter to generate)"
            class="resize-none text-sm"
            @keydown="onPromptKeydown"
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
          <!-- Optional source image -->
          <div
            class="rounded-xl border border-dashed transition-colors p-3 text-center text-sm"
            :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div v-if="source" class="flex items-center gap-3">
              <img :src="source.url" class="size-14 rounded object-cover border" />
              <span class="text-xs text-muted-foreground flex-1 text-left truncate">
                Editing <strong>{{ source.name }}</strong> with your prompt
              </span>
              <Button variant="ghost" size="icon" @click="clearSource"><X class="size-4" /></Button>
            </div>
            <div v-else class="text-muted-foreground">
              <Upload class="size-4 inline mr-1 opacity-60" />
              Drag an image to <em>edit</em> it, or
              <button class="text-primary underline" @click="fileInput?.click()">browse</button>
              <span class="text-[11px]"> (optional)</span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFiles" />
          </div>

          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ source ? 'Edit mode' : 'Generate mode' }}</span>
            <ElapsedTimer :running="running" class="text-xs text-muted-foreground" />
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component :is="running ? Loader2 : Sparkles" class="size-4" :class="running ? 'animate-spin' : ''" />
                {{ source ? 'Edit' : 'Generate' }}
              </Button>
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
          <Label class="text-xs text-muted-foreground">Aspect ratio</Label>
          <Select v-model="size">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="p in ASPECT_PRESETS"
                :key="`${p.w}x${p.h}`"
                :value="`${p.w}x${p.h}`"
                class="text-sm"
              >
                {{ p.label }} · {{ p.ratio }}
              </SelectItem>
            </SelectContent>
          </Select>

          <!-- Live shape preview -->
          <div class="mt-2 flex h-32 items-center justify-center rounded-lg border bg-muted/30 p-3">
            <div
              class="rounded border-2 border-primary/50 bg-primary/10"
              :style="{
                aspectRatio: `${currentPreset.w} / ${currentPreset.h}`,
                maxWidth: '100%',
                maxHeight: '100%',
                ...(currentPreset.w >= currentPreset.h ? { width: '100%' } : { height: '100%' }),
              }"
            />
          </div>
          <p class="mt-1 text-center text-[11px] text-muted-foreground tabular-nums">
            {{ currentPreset.w }} × {{ currentPreset.h }}
          </p>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Number of images</Label>
          <Input v-model.number="n" type="number" min="1" max="4" class="mt-1 h-8 text-sm" />
        </div>
        <p class="text-[11px] text-muted-foreground">
          Images are generated on a provider's GPU and stored on inference.club.
        </p>
      </Card>
    </div>
  </div>
</template>
