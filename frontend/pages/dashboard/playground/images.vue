<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ChevronDown, Clock, Download, Image as ImageIcon, Lightbulb, Loader2, Sparkles, Square, Upload, X } from 'lucide-vue-next'
import { useImageGeneration, type GeneratedImage } from '@/composables/useImageGeneration'
import { useImageLightbox } from '@/composables/useImageLightbox'
import { SUGGESTED_IMAGE_PROMPTS } from '@/utils/imagePrompts'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { listImageModels, generate, edit } = useImageGeneration()
const lightbox = useImageLightbox()

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
const size = ref('1024x1024')
const n = ref(1)
const SIZES = ['256x256', '512x512', '768x768', '1024x1024']

// Optional source image → switches to the edit endpoint.
interface SourceImage { blob: Blob; name: string; url: string }
const source = ref<SourceImage | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const MAX_MB = 25

const running = ref(false)
let controller: AbortController | null = null

interface ResultRow {
  id: string
  prompt: string
  sourceUrl?: string
  images: GeneratedImage[]
  latencyMs: number
  model: string
}
const results = ref<ResultRow[]>([])

const uid = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.round(Math.random() * 1e9)}`

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
  const start = performance.now()
  const p = prompt.value.trim()
  const src = source.value
  try {
    const images = src
      ? await edit(src.blob, src.name, { model: model.value, prompt: p, n: n.value, size: size.value }, controller.signal)
      : await generate({ model: model.value, prompt: p, n: n.value, size: size.value }, controller.signal)
    results.value.unshift({
      id: uid(),
      prompt: p,
      sourceUrl: src ? URL.createObjectURL(src.blob) : undefined,
      images,
      latencyMs: Math.round(performance.now() - start),
      model: model.value,
    })
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

const download = (url: string, i: number) => {
  const a = document.createElement('a')
  a.href = url
  a.download = `image-${i}.png`
  a.target = '_blank'
  a.click()
}

onMounted(async () => {
  try {
    models.value = await listImageModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
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
  results.value.forEach((r) => r.sourceUrl && URL.revokeObjectURL(r.sourceUrl))
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
            placeholder="A watercolor fox in a misty forest at dawn…"
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

        <!-- Results -->
        <Card v-for="r in results" :key="r.id" class="p-4 space-y-3">
          <div class="flex items-center gap-2 flex-wrap text-[11px] text-muted-foreground">
            <Badge variant="outline" class="font-mono">{{ r.model }}</Badge>
            <span class="inline-flex items-center gap-1"><Clock class="size-3" /> {{ r.latencyMs }} ms</span>
            <span class="truncate flex-1">{{ r.prompt }}</span>
          </div>
          <div class="flex flex-wrap gap-3">
            <div v-if="r.sourceUrl" class="relative">
              <img
                :src="r.sourceUrl"
                class="max-h-64 cursor-zoom-in rounded-lg border opacity-80 transition-opacity hover:opacity-100"
                @click="lightbox.open(r.sourceUrl)"
              />
              <Badge class="absolute top-1.5 left-1.5" variant="secondary">source</Badge>
            </div>
            <div v-for="(img, i) in r.images" :key="i" class="relative group">
              <img
                v-if="img.url"
                :src="img.url"
                class="max-h-64 cursor-zoom-in rounded-lg border transition-opacity hover:opacity-90"
                @click="lightbox.open(img.url)"
              />
              <Button
                v-if="img.url"
                variant="secondary"
                size="icon"
                class="absolute top-1.5 right-1.5 size-7 opacity-0 group-hover:opacity-100 transition-opacity"
                @click="download(img.url, i)"
              >
                <Download class="size-3.5" />
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Size</Label>
          <Select v-model="size">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="s in SIZES" :key="s" :value="s" class="text-sm">{{ s }}</SelectItem>
            </SelectContent>
          </Select>
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
