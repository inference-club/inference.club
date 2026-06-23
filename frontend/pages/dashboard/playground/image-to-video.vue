<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  Check, Clapperboard, Film, ImageIcon, ImagePlus, Loader2, Pencil, RefreshCw,
  Sparkles, Square, Upload, Wand2, X,
} from 'lucide-vue-next'
import { useImageToVideo } from '@/composables/useImageToVideo'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.imageToVideo' })

const { listModels, generateImage, suggestPrompts, generateVideo } = useImageToVideo()

// --- models ----------------------------------------------------------------
const imageModels = ref<ModelInfo[]>([])
const chatModels = ref<ModelInfo[]>([])
const videoModels = ref<ModelInfo[]>([])
const imageModel = ref('')
const chatModel = ref('')
const videoModel = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// A chat model is vision-capable if it accepts image input.
const isVision = (m: ModelInfo) => (m.input_modalities ?? []).includes('image')
const selectedChatVision = computed(() => {
  const m = chatModels.value.find((x) => x.id === chatModel.value)
  return m ? isVision(m) : false
})

// =====================================================================
// STAGE 1 — Image
// =====================================================================
type ImageMode = 'generate' | 'upload'
const imageMode = ref<ImageMode>('generate')

const imagePrompt = ref('')
const DIM_PRESETS = [512, 768, 1024]
const imgWidth = ref(768)
const imgHeight = ref(768)

// The resulting first frame (data URI) + its pixel dimensions.
const frame = ref<string | null>(null)
const frameW = ref(768)
const frameH = ref(768)

const imgRunning = ref(false)
let imgController: AbortController | null = null

const canGenerateImage = computed(
  () => !!imageModel.value && !!imagePrompt.value.trim() && !imgRunning.value,
)

const runImage = async () => {
  if (!canGenerateImage.value) return
  imgRunning.value = true
  imgController = new AbortController()
  try {
    const dataUri = await generateImage(
      {
        model: imageModel.value,
        prompt: imagePrompt.value.trim(),
        size: `${imgWidth.value}x${imgHeight.value}`,
      },
      imgController.signal,
    )
    setFrame(dataUri, imgWidth.value, imgHeight.value)
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Image generation failed')
  } finally {
    imgRunning.value = false
    imgController = null
  }
}
const stopImage = () => imgController?.abort()

const setFrame = (dataUri: string, w: number, h: number) => {
  frame.value = dataUri
  frameW.value = w
  frameH.value = h
  // Default the render size to the frame's dimensions (clamped below).
  vidWidth.value = clampDim(w)
  vidHeight.value = clampDim(h)
  // Reset downstream stages.
  description.value = ''
  candidates.value = []
  chosenPrompt.value = ''
}

// Upload path: read a File → data URI and measure it.
const fileInput = ref<HTMLInputElement | null>(null)
const MAX_MB = 25
const onUpload = (e: Event) => {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (fileInput.value) fileInput.value.value = ''
  if (!f) return
  if (!f.type.startsWith('image/')) return toast.error('Pick an image file.')
  if (f.size > MAX_MB * 1024 * 1024) return toast.error(`That image is over ${MAX_MB}MB.`)
  const fr = new FileReader()
  fr.onload = () => {
    const url = String(fr.result)
    const img = new Image()
    img.onload = () => setFrame(url, img.naturalWidth, img.naturalHeight)
    img.onerror = () => toast.error('Could not read that image.')
    img.src = url
  }
  fr.onerror = () => toast.error('Could not read that file.')
  fr.readAsDataURL(f)
}

// =====================================================================
// STAGE 2 — Video prompt
// =====================================================================
type PromptMode = 'write' | 'lazy'
const promptMode = ref<PromptMode>('write')

const description = ref('')
const candidates = ref<string[]>([])
const chosenPrompt = ref('') // the prompt actually used for render
const editingIdx = ref<number | null>(null)
const extraInstructions = ref('')

const PROMPT_COUNT = 3
const suggesting = ref(false)
let suggestController: AbortController | null = null

const runSuggest = async (more = false) => {
  if (!frame.value) return toast.error('Create or upload an image first.')
  if (!chatModel.value) return toast.error('Pick a chat model.')
  suggesting.value = true
  suggestController = new AbortController()
  try {
    const res = await suggestPrompts(
      {
        model: chatModel.value,
        imageDataUri: frame.value,
        count: PROMPT_COUNT,
        duration: duration.value,
        avoid: more ? candidates.value : [],
        extra: extraInstructions.value,
      },
      suggestController.signal,
    )
    if (res.description) description.value = res.description
    if (more) candidates.value = [...candidates.value, ...res.prompts]
    else candidates.value = res.prompts
    if (!res.prompts.length) toast.error('The model returned no prompts — try again.')
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Prompt suggestion failed')
  } finally {
    suggesting.value = false
    suggestController = null
  }
}
const stopSuggest = () => suggestController?.abort()

const pickCandidate = (p: string) => {
  chosenPrompt.value = p
}

// =====================================================================
// STAGE 3 — Render
// =====================================================================
const duration = ref(5)
const vidWidth = ref(768)
const vidHeight = ref(768)

// The endpoint accepts width/height in [64, 1920]. Keep it LTX-friendly: clamp
// and snap to a multiple of 32.
const clampDim = (n: number) => {
  const c = Math.max(256, Math.min(1280, Math.round(n)))
  return Math.round(c / 32) * 32
}

const result = ref<{ url: string; contentType: string } | null>(null)
const rendering = ref(false)
let renderController: AbortController | null = null

const effectivePrompt = computed(() =>
  (promptMode.value === 'lazy' ? chosenPrompt.value : ownPrompt.value).trim(),
)
const ownPrompt = ref('')

const canRender = computed(
  () => !!videoModel.value && !!frame.value && !!effectivePrompt.value && !rendering.value,
)

const runRender = async () => {
  if (!canRender.value || !frame.value) return
  rendering.value = true
  renderController = new AbortController()
  if (result.value) URL.revokeObjectURL(result.value.url)
  result.value = null
  try {
    const video = await generateVideo(
      {
        model: videoModel.value,
        prompt: effectivePrompt.value,
        image: frame.value,
        duration: duration.value,
        width: clampDim(vidWidth.value),
        height: clampDim(vidHeight.value),
      },
      renderController.signal,
    )
    result.value = { url: video.url, contentType: video.contentType }
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Video render failed')
  } finally {
    rendering.value = false
    renderController = null
  }
}
const stopRender = () => renderController?.abort()

const download = () => {
  if (!result.value) return
  const a = document.createElement('a')
  a.href = result.value.url
  a.download = 'image-to-video.mp4'
  a.click()
}

// =====================================================================
// Lifecycle
// =====================================================================
onMounted(async () => {
  try {
    const all = await listModels()
    imageModels.value = all.filter((m) => m.service_type === 'image')
    videoModels.value = all.filter((m) => m.service_type === 'video')
    chatModels.value = all.filter((m) => m.service_type === 'llm')
    if (imageModels.value.length) imageModel.value = imageModels.value[0].id
    if (videoModels.value.length) videoModel.value = videoModels.value[0].id
    // Prefer a vision-capable chat model (e.g. nemotron-omni) by default.
    const vision = chatModels.value.find(isVision)
    chatModel.value = (vision || chatModels.value[0])?.id || ''

    const missing: string[] = []
    if (!videoModels.value.length) missing.push('a video model (service_type: video, e.g. LTX-2)')
    if (!chatModels.value.length) missing.push('a chat/vision model')
    if (missing.length) {
      modelsError.value = `Some stages are unavailable: you need ${missing.join(' and ')}.`
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  imgController?.abort()
  suggestController?.abort()
  renderController?.abort()
  if (result.value) URL.revokeObjectURL(result.value.url)
})
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-3 sm:px-6 py-6 space-y-6">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Clapperboard class="h-6 w-6" /> Image → Video
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        Make a first frame, let the AI pitch funny continuations, then render a short video — all in one guided flow.
      </p>
    </div>

    <div v-if="modelsError" class="p-3 bg-muted text-muted-foreground rounded text-sm">
      {{ modelsError }}
    </div>

    <!-- ============================================================= -->
    <!-- STAGE 1 — Image -->
    <!-- ============================================================= -->
    <Card class="p-4 space-y-4">
      <div class="flex items-center gap-2">
        <span class="flex size-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">1</span>
        <h2 class="text-sm font-semibold uppercase tracking-wide">First frame</h2>
      </div>

      <div class="flex gap-2">
        <Button :variant="imageMode === 'generate' ? 'default' : 'outline'" size="sm" class="gap-1.5" @click="imageMode = 'generate'">
          <Sparkles class="size-4" /> Generate
        </Button>
        <Button :variant="imageMode === 'upload' ? 'default' : 'outline'" size="sm" class="gap-1.5" @click="imageMode = 'upload'">
          <Upload class="size-4" /> Upload
        </Button>
      </div>

      <!-- Generate mode -->
      <div v-if="imageMode === 'generate'" class="space-y-3">
        <div class="flex flex-wrap items-end gap-3">
          <div class="min-w-[16rem] flex-1">
            <Label class="text-xs text-muted-foreground">Model</Label>
            <Select v-model="imageModel" :disabled="loadingModels || !imageModels.length">
              <SelectTrigger class="mt-1 h-8 font-mono text-xs">
                <SelectValue :placeholder="loadingModels ? 'Loading…' : (imageModels.length ? 'Select' : 'No image models')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="m in imageModels" :key="m.id" :value="m.id" class="font-mono text-xs">{{ m.id }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Image description</Label>
          <Textarea
            v-model="imagePrompt"
            rows="2"
            placeholder="e.g. a grumpy cat in a tiny business suit sitting at a desk, soft window light"
            class="mt-1 resize-none text-sm"
          />
        </div>

        <!-- Dimensions -->
        <div class="grid grid-cols-2 gap-3 sm:max-w-md">
          <div>
            <Label class="text-xs text-muted-foreground">Width</Label>
            <Input v-model.number="imgWidth" type="number" min="256" max="1280" step="32" class="mt-1 h-8 text-sm tabular-nums" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Height</Label>
            <Input v-model.number="imgHeight" type="number" min="256" max="1280" step="32" class="mt-1 h-8 text-sm tabular-nums" />
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="text-[11px] text-muted-foreground mr-1">Presets:</span>
          <Button
            v-for="d in DIM_PRESETS"
            :key="d"
            variant="outline"
            size="sm"
            class="h-7 px-2 text-xs"
            @click="imgWidth = d; imgHeight = d"
          >
            {{ d }}×{{ d }}
          </Button>
        </div>

        <div class="flex items-center gap-2">
          <Button v-if="imgRunning" variant="destructive" size="sm" class="gap-2" @click="stopImage">
            <Square class="size-4" /> Stop
          </Button>
          <Button :disabled="!canGenerateImage" size="sm" class="gap-2" @click="runImage">
            <component :is="imgRunning ? Loader2 : ImagePlus" class="size-4" :class="imgRunning ? 'animate-spin' : ''" />
            Generate image
          </Button>
        </div>
      </div>

      <!-- Upload mode -->
      <div v-else class="space-y-2">
        <button
          type="button"
          class="w-full rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground hover:bg-accent/40"
          @click="fileInput?.click()"
        >
          <Upload class="size-5 inline mr-1 opacity-60" />
          Click to upload an image (max {{ MAX_MB }}MB)
        </button>
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onUpload" />
      </div>

      <!-- Frame preview -->
      <div v-if="frame" class="flex items-start gap-3 border-t pt-3">
        <img :src="frame" class="max-h-48 rounded-lg border object-contain" />
        <div class="text-xs text-muted-foreground space-y-1">
          <p class="flex items-center gap-1 text-foreground"><Check class="size-3.5 text-green-600" /> First frame ready</p>
          <p>{{ frameW }} × {{ frameH }} px</p>
          <Button variant="ghost" size="sm" class="h-7 gap-1.5 px-2 text-xs" @click="frame = null">
            <X class="size-3.5" /> Clear
          </Button>
        </div>
      </div>
    </Card>

    <!-- ============================================================= -->
    <!-- STAGE 2 — Video prompt -->
    <!-- ============================================================= -->
    <Card class="p-4 space-y-4" :class="frame ? '' : 'opacity-60 pointer-events-none'">
      <div class="flex items-center gap-2">
        <span class="flex size-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">2</span>
        <h2 class="text-sm font-semibold uppercase tracking-wide">What happens in the video?</h2>
      </div>

      <div class="flex gap-2">
        <Button :variant="promptMode === 'write' ? 'default' : 'outline'" size="sm" class="gap-1.5" @click="promptMode = 'write'">
          <Pencil class="size-4" /> Write my own
        </Button>
        <Button :variant="promptMode === 'lazy' ? 'default' : 'outline'" size="sm" class="gap-1.5" @click="promptMode = 'lazy'">
          <Wand2 class="size-4" /> I'm feeling lazy
        </Button>
      </div>

      <!-- Write-my-own -->
      <div v-if="promptMode === 'write'">
        <Label class="text-xs text-muted-foreground">Describe the motion that brings the frame to life</Label>
        <Textarea
          v-model="ownPrompt"
          rows="4"
          placeholder="e.g. the cat slowly turns to the camera, deadpan, then knocks the pencil cup off the desk; a tiny cartoonish crash; soft jazz underneath"
          class="mt-1 resize-none text-sm"
        />
      </div>

      <!-- AI assist -->
      <div v-else class="space-y-3">
        <div class="flex flex-wrap items-end gap-3">
          <div class="min-w-[16rem] flex-1">
            <Label class="text-xs text-muted-foreground">Vision model</Label>
            <Select v-model="chatModel" :disabled="loadingModels || !chatModels.length">
              <SelectTrigger class="mt-1 h-8 font-mono text-xs">
                <SelectValue :placeholder="loadingModels ? 'Loading…' : (chatModels.length ? 'Select' : 'No chat models')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="m in chatModels" :key="m.id" :value="m.id" class="font-mono text-xs">
                  <span class="flex items-center gap-2">
                    <span class="truncate">{{ m.id }}</span>
                    <ImageIcon v-if="isVision(m)" class="size-3 text-muted-foreground shrink-0" />
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <p v-if="chatModel && !selectedChatVision" class="text-[11px] text-amber-600 dark:text-amber-500">
          This model doesn't advertise image input — pick a vision-capable model (e.g. nemotron-omni) for best results.
        </p>

        <div>
          <Label class="text-xs text-muted-foreground">Extra instructions (optional)</Label>
          <Input v-model="extraInstructions" placeholder="e.g. keep it wholesome, make it absurd, no dialogue" class="mt-1 h-8 text-sm" />
        </div>

        <div class="flex items-center gap-2">
          <Button v-if="suggesting" variant="destructive" size="sm" class="gap-2" @click="stopSuggest">
            <Square class="size-4" /> Stop
          </Button>
          <template v-else>
            <Button size="sm" class="gap-2" @click="runSuggest(false)">
              <Wand2 class="size-4" /> {{ candidates.length ? 'Regenerate' : 'Suggest prompts' }}
            </Button>
            <Button v-if="candidates.length" variant="outline" size="sm" class="gap-2" @click="runSuggest(true)">
              <RefreshCw class="size-4" /> Generate more
            </Button>
          </template>
          <Loader2 v-if="suggesting" class="size-4 animate-spin text-muted-foreground" />
        </div>

        <p v-if="description" class="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
          The model sees: {{ description }}
        </p>

        <!-- Candidate list -->
        <div v-if="candidates.length" class="space-y-2">
          <div
            v-for="(c, i) in candidates"
            :key="i"
            class="rounded-lg border p-3 text-sm transition-colors"
            :class="chosenPrompt === c ? 'border-primary bg-primary/5' : 'border-border'"
          >
            <div class="flex items-start gap-2">
              <Textarea
                v-if="editingIdx === i"
                v-model="candidates[i]"
                rows="4"
                class="flex-1 resize-none text-sm"
              />
              <p v-else class="flex-1 whitespace-pre-wrap">{{ c }}</p>
            </div>
            <div class="mt-2 flex items-center gap-1.5">
              <Button
                :variant="chosenPrompt === c ? 'default' : 'outline'"
                size="sm"
                class="h-7 gap-1.5 px-2 text-xs"
                @click="pickCandidate(c)"
              >
                <Check class="size-3.5" /> {{ chosenPrompt === c ? 'Picked' : 'Use this' }}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                class="h-7 gap-1.5 px-2 text-xs"
                @click="editingIdx === i ? (editingIdx = null) : (editingIdx = i)"
              >
                <Pencil class="size-3.5" /> {{ editingIdx === i ? 'Done' : 'Edit' }}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Card>

    <!-- ============================================================= -->
    <!-- STAGE 3 — Render -->
    <!-- ============================================================= -->
    <Card class="p-4 space-y-4" :class="frame && effectivePrompt ? '' : 'opacity-60 pointer-events-none'">
      <div class="flex items-center gap-2">
        <span class="flex size-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">3</span>
        <h2 class="text-sm font-semibold uppercase tracking-wide">Render</h2>
      </div>

      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[16rem] flex-1">
          <Label class="text-xs text-muted-foreground">Video model</Label>
          <Select v-model="videoModel" :disabled="loadingModels || !videoModels.length">
            <SelectTrigger class="mt-1 h-8 font-mono text-xs">
              <SelectValue :placeholder="loadingModels ? 'Loading…' : (videoModels.length ? 'Select' : 'No video models')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="m in videoModels" :key="m.id" :value="m.id" class="font-mono text-xs">{{ m.id }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3 sm:max-w-lg">
        <div>
          <Label class="text-xs text-muted-foreground">Duration: {{ duration }}s</Label>
          <Input v-model.number="duration" type="range" min="1" max="10" step="1" class="mt-1 w-full" />
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Width</Label>
          <Input v-model.number="vidWidth" type="number" min="256" max="1280" step="32" class="mt-1 h-8 text-sm tabular-nums" />
        </div>
        <div>
          <Label class="text-xs text-muted-foreground">Height</Label>
          <Input v-model.number="vidHeight" type="number" min="256" max="1280" step="32" class="mt-1 h-8 text-sm tabular-nums" />
        </div>
      </div>

      <!-- The prompt being rendered -->
      <div v-if="effectivePrompt" class="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
        <span class="font-semibold text-foreground">Prompt:</span> {{ effectivePrompt }}
      </div>

      <p class="text-[11px] text-muted-foreground">
        LTX renders motion from your prompt; dialogue &amp; sound effects shape the action and timing — audio playback depends on the model.
      </p>

      <div class="flex items-center gap-2">
        <Button v-if="rendering" variant="destructive" size="sm" class="gap-2" @click="stopRender">
          <Square class="size-4" /> Stop
        </Button>
        <Button :disabled="!canRender" size="sm" class="gap-2" @click="runRender">
          <component :is="rendering ? Loader2 : Film" class="size-4" :class="rendering ? 'animate-spin' : ''" />
          Render video
        </Button>
      </div>

      <!-- In-flight notice (rendering is slow) -->
      <Card v-if="rendering" class="p-3 flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 class="size-4 animate-spin shrink-0" />
        <span class="flex-1">Rendering your video — this can take a couple of minutes…</span>
        <ElapsedTimer :running="rendering" class="shrink-0 font-medium text-foreground" />
      </Card>

      <!-- Result -->
      <div v-if="result" class="space-y-2 border-t pt-3">
        <video :src="result.url" controls playsinline class="w-full rounded-lg border bg-black" />
        <div class="flex items-center gap-2">
          <Button variant="outline" size="sm" class="gap-1.5" @click="download">
            <Film class="size-4" /> Download MP4
          </Button>
        </div>
        <p class="text-[11px] text-muted-foreground">
          Saved video generations also appear under Media → Videos.
        </p>
      </div>
    </Card>
  </div>
</template>
