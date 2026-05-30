<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  Bot,
  Send as SendIcon,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  User,
} from 'lucide-vue-next'
import { usePlayground, type ChatUsage } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

interface Msg {
  role: 'user' | 'assistant'
  content: string
  reasoning: string
  usage?: ChatUsage
  tps?: number
  done: boolean
  error?: boolean
}

const { listModels, sendChat } = usePlayground()

const models = ref<string[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// Generation parameters. Sliders hold numbers; optional fields are strings so
// "blank" means "don't send it" (let the server pick its default).
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

const input = ref('')
const messages = ref<Msg[]>([])
const sending = ref(false)
const showParams = ref(false) // mobile toggle; the panel is always shown on lg
const scroller = ref<HTMLElement | null>(null)
let controller: AbortController | null = null

const canSend = computed(() => !!model.value && !!input.value.trim() && !sending.value)

const scrollDown = async () => {
  await nextTick()
  scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
}

const num = (v: string) => {
  const n = Number(v)
  return v.trim() !== '' && !Number.isNaN(n) ? n : undefined
}

const setSlider = (key: 'temperature' | 'top_p' | 'frequency_penalty' | 'presence_penalty', v?: number[]) => {
  if (v && v.length) params[key] = v[0]
}

const buildBody = (history: Msg[]) => {
  const msgs: { role: string; content: string }[] = []
  if (system.value.trim()) msgs.push({ role: 'system', content: system.value })
  for (const m of history) msgs.push({ role: m.role, content: m.content })

  const body: Record<string, unknown> = {
    model: model.value,
    messages: msgs,
    stream: stream.value,
    temperature: params.temperature,
    top_p: params.top_p,
    frequency_penalty: params.frequency_penalty,
    presence_penalty: params.presence_penalty,
  }
  const max = num(params.max_tokens)
  if (max !== undefined) body.max_tokens = max
  const topk = num(params.top_k)
  if (topk !== undefined) body.top_k = topk
  const minp = num(params.min_p)
  if (minp !== undefined) body.min_p = minp
  const rep = num(params.repetition_penalty)
  if (rep !== undefined) body.repetition_penalty = rep
  const seed = num(params.seed)
  if (seed !== undefined) body.seed = seed
  const stops = params.stop.split(',').map((s) => s.trim()).filter(Boolean)
  if (stops.length) body.stop = stops
  return body
}

const send = async () => {
  if (!canSend.value) return
  const text = input.value.trim()
  input.value = ''
  messages.value.push({ role: 'user', content: text, reasoning: '', done: true })
  const history = messages.value.slice() // user turn + prior context, no empty assistant yet

  const assistant = reactive<Msg>({ role: 'assistant', content: '', reasoning: '', done: false })
  messages.value.push(assistant)
  sending.value = true
  controller = new AbortController()
  await scrollDown()

  const start = performance.now()
  try {
    await sendChat(buildBody(history), {
      signal: controller.signal,
      onText: (c) => {
        assistant.content += c
        scrollDown()
      },
      onReasoning: (c) => {
        assistant.reasoning += c
        scrollDown()
      },
      onUsage: (u) => {
        assistant.usage = u
      },
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
  if (!sending.value) messages.value = []
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

onMounted(async () => {
  try {
    models.value = await listModels()
    if (models.value.length) model.value = models.value[0]
    else modelsError.value = 'No models are available to you right now.'
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
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Sparkles class="h-6 w-6" /> Playground
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Chat with any model you can reach, straight from your account — no API key needed.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Select v-model="model" :disabled="loadingModels || !models.length">
          <SelectTrigger class="w-[16rem] font-mono text-xs">
            <SelectValue :placeholder="loadingModels ? 'Loading models…' : 'Select a model'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="m in models" :key="m" :value="m" class="font-mono text-xs">
              {{ m }}
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

    <div class="flex flex-col lg:flex-row gap-4">
      <!-- Chat column -->
      <Card class="flex-1 min-w-0 flex flex-col">
        <div
          ref="scroller"
          class="flex-1 overflow-y-auto p-4 space-y-4 min-h-[45vh] max-h-[62vh]"
        >
          <div
            v-if="!messages.length"
            class="h-full min-h-[40vh] flex flex-col items-center justify-center text-center text-muted-foreground"
          >
            <Bot class="size-10 mb-3 opacity-40" />
            <p class="text-sm">Send a message to start the conversation.</p>
            <p class="text-xs mt-1">Tune the system prompt and sampling on the right.</p>
          </div>

          <div v-for="(m, i) in messages" :key="i" class="flex gap-3">
            <div
              class="size-8 shrink-0 rounded-full flex items-center justify-center"
              :class="m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'"
            >
              <User v-if="m.role === 'user'" class="size-4" />
              <Bot v-else class="size-4" />
            </div>
            <div class="min-w-0 flex-1 pt-1">
              <!-- Reasoning trace -->
              <details
                v-if="m.reasoning"
                class="mb-2 rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20"
                open
              >
                <summary class="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                  Thinking
                </summary>
                <pre class="px-3 pb-2 text-xs whitespace-pre-wrap text-amber-900/80 dark:text-amber-200/70 font-sans">{{ m.reasoning }}</pre>
              </details>

              <!-- Body -->
              <div
                v-if="m.error"
                class="text-sm text-destructive bg-destructive/10 rounded px-3 py-2"
              >
                {{ m.content }}
              </div>
              <pre
                v-else-if="m.role === 'user' || !m.done"
                class="text-sm whitespace-pre-wrap font-sans"
              >{{ m.content || (sending ? '…' : '') }}</pre>
              <MarkdownRenderer v-else :content="m.content" />

              <!-- Usage footer -->
              <div
                v-if="m.done && m.usage"
                class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground"
              >
                <span v-if="m.usage.prompt_tokens != null">↑ {{ m.usage.prompt_tokens }} in</span>
                <span v-if="m.usage.completion_tokens != null">↓ {{ m.usage.completion_tokens }} out</span>
                <span v-if="m.usage.total_tokens != null">Σ {{ m.usage.total_tokens }} total</span>
                <span v-if="m.tps">{{ m.tps.toFixed(1) }} tok/s</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Composer -->
        <div class="border-t p-3">
          <div class="flex items-end gap-2">
            <Textarea
              v-model="input"
              placeholder="Send a message…  (Enter to send, Shift+Enter for newline)"
              rows="2"
              class="resize-none"
              :disabled="!model"
              @keydown="onKeydown"
            />
            <Button v-if="sending" variant="destructive" size="icon" class="h-10 w-10 shrink-0" @click="stop">
              <Square class="size-4" />
            </Button>
            <Button v-else size="icon" class="h-10 w-10 shrink-0" :disabled="!canSend" @click="send">
              <SendIcon class="size-4" />
            </Button>
          </div>
        </div>
      </Card>

      <!-- Parameters panel -->
      <aside :class="[showParams ? 'block' : 'hidden', 'lg:block lg:w-80 shrink-0']">
        <Card class="p-4 space-y-5">
          <div>
            <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System prompt</Label>
            <Textarea
              v-model="system"
              rows="3"
              placeholder="You are a helpful assistant…"
              class="mt-1.5 resize-none text-sm"
            />
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
              <Slider :model-value="[params.temperature]" :min="0" :max="2" :step="0.01"
                @update:model-value="(v) => setSlider('temperature', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Top P</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.top_p.toFixed(2) }}</span>
              </div>
              <Slider :model-value="[params.top_p]" :min="0" :max="1" :step="0.01"
                @update:model-value="(v) => setSlider('top_p', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Frequency penalty</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.frequency_penalty.toFixed(1) }}</span>
              </div>
              <Slider :model-value="[params.frequency_penalty]" :min="-2" :max="2" :step="0.1"
                @update:model-value="(v) => setSlider('frequency_penalty', v)" />
            </div>
            <div>
              <div class="flex justify-between text-sm mb-1.5">
                <Label>Presence penalty</Label>
                <span class="text-muted-foreground tabular-nums">{{ params.presence_penalty.toFixed(1) }}</span>
              </div>
              <Slider :model-value="[params.presence_penalty]" :min="-2" :max="2" :step="0.1"
                @update:model-value="(v) => setSlider('presence_penalty', v)" />
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
          <p class="text-[11px] text-muted-foreground leading-relaxed">
            Optional fields are only sent when filled. Top K / Min P / repetition penalty are
            forwarded to the engine and may be ignored by models that don't support them.
          </p>
        </Card>
      </aside>
    </div>
  </div>
</template>
