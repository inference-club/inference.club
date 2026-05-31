<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowUp,
  Bot,
  Mic,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  User,
  Video,
  X,
} from 'lucide-vue-next'
import { usePlayground, type ChatUsage, type ModelInfo } from '@/composables/usePlayground'
import { MODALITY_META } from '@/utils/modelCapabilities'

definePageMeta({ layout: 'app' })

type MediaKind = 'image' | 'audio' | 'video'
interface Attachment {
  id: string
  kind: MediaKind
  name: string
  dataUrl: string
  mime: string
}
interface Msg {
  role: 'user' | 'assistant'
  content: string
  reasoning: string
  attachments?: Attachment[]
  usage?: ChatUsage
  tps?: number
  done: boolean
  error?: boolean
}

const { listModels, sendChat } = usePlayground()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')
const selected = computed(() => models.value.find((m) => m.id === model.value))
const caps = computed(() => selected.value?.input_modalities ?? ['text'])
const features = computed(() => selected.value?.supported_features ?? [])
const mediaKinds = computed(
  () => caps.value.filter((m): m is MediaKind => m === 'image' || m === 'audio' || m === 'video')
)
const acceptAttr = computed(() =>
  mediaKinds.value.map((k) => `${k}/*`).join(',')
)

// --- generation params -----------------------------------------------------
const system = ref('')
const stream = ref(true)
const params = reactive({
  temperature: 0.7,
  top_p: 1,
  frequency_penalty: 0,
  presence_penalty: 0,
  max_tokens: '',
  top_k: '',
  min_p: '',
  repetition_penalty: '',
  seed: '',
  stop: '',
})

// --- chat state ------------------------------------------------------------
const input = ref('')
const attachments = ref<Attachment[]>([])
const messages = ref<Msg[]>([])
const sending = ref(false)
const showParams = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const bottomAnchor = ref<HTMLElement | null>(null)
let controller: AbortController | null = null

const MAX_FILE_MB = 20
const micSupported = ref(false)
const recording = ref(false)
let recorder: MediaRecorder | null = null
let recChunks: BlobPart[] = []

const canSend = computed(
  () => !!model.value && !sending.value && (!!input.value.trim() || attachments.value.length > 0)
)

const uid = () =>
  (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.round(Math.random() * 1e9)}`)

const scrollDown = async () => {
  await nextTick()
  bottomAnchor.value?.scrollIntoView({ block: 'end' })
  // Fall back to the window so the message clears the sticky composer at rest.
  window.scrollTo({ top: document.documentElement.scrollHeight })
}

// --- attachments -----------------------------------------------------------
const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = reject
    r.readAsDataURL(blob)
  })

const kindFromMime = (mime: string): MediaKind | null => {
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('video/')) return 'video'
  return null
}

const onFiles = async (e: Event) => {
  const files = Array.from((e.target as HTMLInputElement).files ?? [])
  for (const f of files) {
    const kind = kindFromMime(f.type)
    if (!kind || !mediaKinds.value.includes(kind)) {
      toast.error(`${f.name}: this model doesn't accept ${f.type || 'that file type'}`)
      continue
    }
    if (f.size > MAX_FILE_MB * 1024 * 1024) {
      toast.error(`${f.name} is too large (max ${MAX_FILE_MB} MB)`)
      continue
    }
    attachments.value.push({ id: uid(), kind, name: f.name, dataUrl: await blobToDataUrl(f), mime: f.type })
  }
  if (fileInput.value) fileInput.value.value = '' // allow re-selecting the same file
}

const removeAttachment = (id: string) => {
  attachments.value = attachments.value.filter((a) => a.id !== id)
}

// --- mic recording ---------------------------------------------------------
const toggleMic = async () => {
  if (recording.value) {
    recorder?.stop()
    return
  }
  try {
    const streamMedia = await navigator.mediaDevices.getUserMedia({ audio: true })
    recChunks = []
    recorder = new MediaRecorder(streamMedia)
    recorder.ondataavailable = (ev) => {
      if (ev.data.size) recChunks.push(ev.data)
    }
    recorder.onstop = async () => {
      streamMedia.getTracks().forEach((t) => t.stop())
      const mime = recorder?.mimeType || 'audio/webm'
      const blob = new Blob(recChunks, { type: mime })
      const ext = mime.includes('ogg') ? 'ogg' : mime.includes('wav') ? 'wav' : 'webm'
      attachments.value.push({
        id: uid(), kind: 'audio', name: `recording.${ext}`,
        dataUrl: await blobToDataUrl(blob), mime,
      })
      recording.value = false
    }
    recorder.start()
    recording.value = true
  } catch {
    toast.error('Microphone access was denied')
  }
}

// --- request building ------------------------------------------------------
const num = (v: string) => {
  const n = Number(v)
  return v.trim() !== '' && !Number.isNaN(n) ? n : undefined
}

const mediaPart = (a: Attachment) => {
  if (a.kind === 'image') return { type: 'image_url', image_url: { url: a.dataUrl } }
  if (a.kind === 'audio') return { type: 'audio_url', audio_url: { url: a.dataUrl } }
  return { type: 'video_url', video_url: { url: a.dataUrl } }
}

const buildBody = (history: Msg[]) => {
  const msgs: { role: string; content: unknown }[] = []
  if (system.value.trim()) msgs.push({ role: 'system', content: system.value })
  for (const m of history) {
    if (m.role === 'user' && m.attachments?.length) {
      const parts: unknown[] = []
      if (m.content) parts.push({ type: 'text', text: m.content })
      for (const a of m.attachments) parts.push(mediaPart(a))
      msgs.push({ role: 'user', content: parts })
    } else {
      msgs.push({ role: m.role, content: m.content })
    }
  }
  const body: Record<string, unknown> = {
    model: model.value,
    messages: msgs,
    stream: stream.value,
    temperature: params.temperature,
    top_p: params.top_p,
    frequency_penalty: params.frequency_penalty,
    presence_penalty: params.presence_penalty,
  }
  const opt = (k: string, v: number | undefined) => {
    if (v !== undefined) body[k] = v
  }
  opt('max_tokens', num(params.max_tokens))
  opt('top_k', num(params.top_k))
  opt('min_p', num(params.min_p))
  opt('repetition_penalty', num(params.repetition_penalty))
  opt('seed', num(params.seed))
  const stops = params.stop.split(',').map((s) => s.trim()).filter(Boolean)
  if (stops.length) body.stop = stops
  return body
}

const send = async () => {
  if (!canSend.value) return
  const text = input.value.trim()
  const atts = attachments.value.slice()
  input.value = ''
  attachments.value = []

  messages.value.push({ role: 'user', content: text, reasoning: '', attachments: atts, done: true })
  const history = messages.value.slice()
  const assistant = reactive<Msg>({ role: 'assistant', content: '', reasoning: '', done: false })
  messages.value.push(assistant)
  sending.value = true
  controller = new AbortController()
  await scrollDown()

  const start = performance.now()
  try {
    await sendChat(buildBody(history), {
      signal: controller.signal,
      onText: (c) => { assistant.content += c; scrollDown() },
      onReasoning: (c) => { assistant.reasoning += c; scrollDown() },
      onUsage: (u) => { assistant.usage = u },
    })
    const elapsed = (performance.now() - start) / 1000
    const ct = assistant.usage?.completion_tokens
    if (ct && elapsed > 0) assistant.tps = ct / elapsed
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name === 'AbortError') {
      assistant.content += assistant.content ? '\n\n_(stopped)_' : '_(stopped)_'
    } else {
      assistant.error = true
      assistant.content = err?.message || 'Request failed'
    }
  } finally {
    assistant.done = true
    sending.value = false
    controller = null
    scrollDown()
  }
}

const stop = () => controller?.abort()
const clear = () => {
  if (!sending.value) {
    messages.value = []
    attachments.value = []
  }
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

const setSlider = (
  key: 'temperature' | 'top_p' | 'frequency_penalty' | 'presence_penalty',
  v?: number[]
) => {
  if (v && v.length) params[key] = v[0]
}

onMounted(async () => {
  micSupported.value = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder)
  try {
    // Chat is for text-generating (LLM) models; transcription-only (STT) and
    // speech (TTS) models live on their own playground surfaces.
    models.value = (await listModels()).filter((m) => m.service_type === 'llm')
    if (models.value.length) {
      // Honor a ?model=<slug> deep-link (e.g. from a public profile CTA);
      // fall back to the first available model.
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
    } else {
      modelsError.value = 'No models are available to you right now.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-6xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Sparkles class="h-6 w-6" /> Playground
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Chat with any model you can reach — text, and whatever else it supports.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Select v-model="model" :disabled="loadingModels || !models.length">
          <SelectTrigger class="w-[18rem] font-mono text-xs">
            <SelectValue :placeholder="loadingModels ? 'Loading models…' : 'Select a model'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="m in models" :key="m.id" :value="m.id" class="font-mono text-xs">
              <span class="flex items-center gap-2">
                <span class="truncate">{{ m.id }}</span>
                <component
                  :is="MODALITY_META[mod]?.icon"
                  v-for="mod in m.input_modalities.filter((x) => x !== 'text')"
                  :key="mod"
                  class="size-3 text-muted-foreground shrink-0"
                />
              </span>
            </SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="icon" class="lg:hidden" @click="showParams = !showParams">
          <SlidersHorizontal class="size-4" />
        </Button>
        <Button variant="outline" size="icon" :disabled="!messages.length || sending" @click="clear">
          <Trash2 class="size-4" />
        </Button>
      </div>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ modelsError }}
    </div>

    <!-- Selected model capabilities -->
    <ModelCapabilities
      v-if="selected"
      class="mb-4"
      :context-length="selected.context_length"
      :input-modalities="caps"
      :supported-features="features"
      show-label
    />

    <div class="flex flex-col lg:flex-row gap-4 lg:items-start">
      <!-- Chat column -->
      <div class="flex-1 min-w-0 flex flex-col">
        <div class="flex-1 space-y-4">
          <div
            v-if="!messages.length"
            class="min-h-[35vh] flex flex-col items-center justify-center text-center text-muted-foreground"
          >
            <Bot class="size-10 mb-3 opacity-40" />
            <p class="text-sm">Send a message to start the conversation.</p>
            <p v-if="mediaKinds.length" class="text-xs mt-1">
              This model also accepts {{ mediaKinds.join(', ') }} — attach with the + button.
            </p>
          </div>

          <div v-for="(m, i) in messages" :key="i" class="flex gap-3">
            <div
              class="size-8 shrink-0 rounded-full flex items-center justify-center"
              :class="m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'"
            >
              <User v-if="m.role === 'user'" class="size-4" />
              <Bot v-else class="size-4" />
            </div>
            <div class="min-w-0 flex-1 pt-1 space-y-2">
              <!-- Reasoning trace -->
              <details
                v-if="m.reasoning"
                class="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20"
                open
              >
                <summary class="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                  Thinking
                </summary>
                <pre class="px-3 pb-2 text-xs whitespace-pre-wrap text-amber-900/80 dark:text-amber-200/70 font-sans">{{ m.reasoning }}</pre>
              </details>

              <!-- Attachments (user) -->
              <div v-if="m.attachments?.length" class="flex flex-wrap gap-2">
                <template v-for="a in m.attachments" :key="a.id">
                  <img v-if="a.kind === 'image'" :src="a.dataUrl" :alt="a.name" class="max-h-48 rounded-lg border" />
                  <audio v-else-if="a.kind === 'audio'" :src="a.dataUrl" controls class="h-10" />
                  <video v-else :src="a.dataUrl" controls class="max-h-48 rounded-lg border" />
                </template>
              </div>

              <!-- Body -->
              <div v-if="m.error" class="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">
                {{ m.content }}
              </div>
              <pre
                v-else-if="m.role === 'user' || !m.done"
                class="text-sm whitespace-pre-wrap font-sans"
              >{{ m.content || (m.role === 'assistant' && sending ? '…' : '') }}</pre>
              <MarkdownRenderer v-else :content="m.content" />

              <!-- Usage -->
              <div
                v-if="m.done && m.usage"
                class="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground"
              >
                <span v-if="m.usage.prompt_tokens != null">↑ {{ m.usage.prompt_tokens }} in</span>
                <span v-if="m.usage.completion_tokens != null">↓ {{ m.usage.completion_tokens }} out</span>
                <span v-if="m.tps">{{ m.tps.toFixed(1) }} tok/s</span>
              </div>
            </div>
          </div>
          <div ref="bottomAnchor" />
        </div>

        <!-- Composer (sticky to the bottom of this section, yields to the footer) -->
        <div class="sticky bottom-0 z-10 bg-gradient-to-t from-background via-background to-transparent pt-4 pb-2">
          <div class="rounded-2xl border bg-background shadow-sm focus-within:ring-1 focus-within:ring-ring transition">
            <!-- Pending attachments -->
            <div v-if="attachments.length" class="flex flex-wrap gap-2 p-3 pb-0">
              <div
                v-for="a in attachments"
                :key="a.id"
                class="relative group rounded-lg border bg-muted/40 overflow-hidden"
              >
                <img v-if="a.kind === 'image'" :src="a.dataUrl" :alt="a.name" class="size-16 object-cover" />
                <div v-else class="size-16 flex flex-col items-center justify-center gap-1 px-1 text-center">
                  <component :is="a.kind === 'audio' ? Mic : Video" class="size-5 text-muted-foreground" />
                  <span class="text-[9px] text-muted-foreground truncate w-full">{{ a.name }}</span>
                </div>
                <button
                  type="button"
                  class="absolute -top-1.5 -right-1.5 size-5 rounded-full bg-foreground text-background flex items-center justify-center opacity-90 hover:opacity-100"
                  @click="removeAttachment(a.id)"
                >
                  <X class="size-3" />
                </button>
              </div>
            </div>

            <!-- Text -->
            <textarea
              v-model="input"
              rows="1"
              :placeholder="model ? 'Send a message…' : 'Select a model first'"
              :disabled="!model"
              class="w-full resize-none bg-transparent px-4 pt-3 pb-1 text-sm outline-none max-h-48 min-h-[2.5rem]"
              @keydown="onKeydown"
              @input="(e) => { const t = e.target as HTMLTextAreaElement; t.style.height='auto'; t.style.height = Math.min(t.scrollHeight, 192) + 'px' }"
            />

            <!-- Bottom row -->
            <div class="flex items-center gap-1 px-2.5 pb-2.5">
              <input
                ref="fileInput"
                type="file"
                multiple
                :accept="acceptAttr"
                class="hidden"
                @change="onFiles"
              />
              <Button
                v-if="mediaKinds.length"
                variant="ghost"
                size="icon"
                class="rounded-full size-9 text-muted-foreground"
                title="Attach files"
                @click="fileInput?.click()"
              >
                <Plus class="size-5" />
              </Button>

              <div class="ml-auto flex items-center gap-1">
                <Button
                  v-if="micSupported && caps.includes('audio')"
                  variant="ghost"
                  size="icon"
                  class="rounded-full size-9"
                  :class="recording ? 'text-red-500 animate-pulse' : 'text-muted-foreground'"
                  :title="recording ? 'Stop recording' : 'Record audio'"
                  @click="toggleMic"
                >
                  <Mic class="size-5" />
                </Button>
                <Button
                  v-if="sending"
                  variant="destructive"
                  size="icon"
                  class="rounded-full size-9"
                  @click="stop"
                >
                  <Square class="size-4" />
                </Button>
                <Button
                  v-else
                  size="icon"
                  class="rounded-full size-9"
                  :disabled="!canSend"
                  @click="send"
                >
                  <ArrowUp class="size-5" />
                </Button>
              </div>
            </div>
          </div>
          <p class="text-[11px] text-muted-foreground text-center mt-1.5">
            Enter to send · Shift+Enter for newline. Image/audio/video support depends on the model + engine.
          </p>
        </div>
      </div>

      <!-- Parameters panel -->
      <aside
        :class="[showParams ? 'block' : 'hidden', 'lg:block lg:w-80 shrink-0 lg:sticky lg:top-4 lg:self-start']"
      >
        <Card class="p-4 space-y-5">
          <div>
            <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System prompt</Label>
            <Textarea v-model="system" rows="3" placeholder="You are a helpful assistant…" class="mt-1.5 resize-none text-sm" />
          </div>

          <div class="flex items-center justify-between">
            <Label for="stream-toggle" class="text-sm">Stream response</Label>
            <Switch id="stream-toggle" v-model="stream" />
          </div>

          <div class="space-y-4 border-t pt-4">
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Temperature</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.temperature.toFixed(2) }}</span>
              </div>
              <Slider :model-value="[params.temperature]" :min="0" :max="2" :step="0.01" @update:model-value="(v) => setSlider('temperature', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Top P</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.top_p.toFixed(2) }}</span>
              </div>
              <Slider :model-value="[params.top_p]" :min="0" :max="1" :step="0.01" @update:model-value="(v) => setSlider('top_p', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Frequency penalty</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.frequency_penalty.toFixed(1) }}</span>
              </div>
              <Slider :model-value="[params.frequency_penalty]" :min="-2" :max="2" :step="0.1" @update:model-value="(v) => setSlider('frequency_penalty', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Presence penalty</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.presence_penalty.toFixed(1) }}</span>
              </div>
              <Slider :model-value="[params.presence_penalty]" :min="-2" :max="2" :step="0.1" @update:model-value="(v) => setSlider('presence_penalty', v)" />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3 border-t pt-4">
            <div>
              <Label class="text-xs text-muted-foreground">Max tokens</Label>
              <Input v-model="params.max_tokens" type="number" min="1" placeholder="auto" class="mt-1 h-8 text-sm" />
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Top K</Label>
              <Input v-model="params.top_k" type="number" min="0" placeholder="off" class="mt-1 h-8 text-sm" />
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Min P</Label>
              <Input v-model="params.min_p" type="number" min="0" max="1" step="0.01" placeholder="off" class="mt-1 h-8 text-sm" />
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Repetition penalty</Label>
              <Input v-model="params.repetition_penalty" type="number" min="0" step="0.01" placeholder="off" class="mt-1 h-8 text-sm" />
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Seed</Label>
              <Input v-model="params.seed" type="number" placeholder="random" class="mt-1 h-8 text-sm" />
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Stop</Label>
              <Input v-model="params.stop" placeholder="a, b" class="mt-1 h-8 text-sm" />
            </div>
          </div>
        </Card>
      </aside>
    </div>
  </div>
</template>
