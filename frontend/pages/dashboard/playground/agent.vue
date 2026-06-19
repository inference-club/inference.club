<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowUp,
  Bot,
  Globe,
  Image as ImageIcon,
  Key,
  Loader2,
  Plus,
  Search,
  Sparkles,
  Square,
  User,
  Wrench,
} from 'lucide-vue-next'
import { usePlayground, type ChatUsage, type ModelInfo } from '@/composables/usePlayground'
import { useAgent, type AgentMedia, type AgentSkill, type AgentTool } from '@/composables/useAgent'
import { useChatThreads, type StoredMessage } from '@/composables/useChatThreads'

definePageMeta({ layout: 'app' })

interface ToolCard {
  id: string
  name: string
  arguments: Record<string, unknown>
  ok?: boolean
  summary?: string
  media?: AgentMedia[]
  done: boolean
}
interface Msg {
  role: 'user' | 'assistant'
  content: string
  reasoning: string
  tools: ToolCard[]
  usage?: ChatUsage
  done: boolean
  error?: boolean
}

const { listModels } = usePlayground()
const { listTools, setBraveKey, runAgent } = useAgent()
const { createThread, updateThread, getThread } = useChatThreads()

const threadId = ref<string | null>(null)
const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')
const tools = ref<AgentTool[]>([])
const skills = ref<AgentSkill[]>([])
const skill = ref('')
const agentEnabled = ref(true)

// --- Brave key management --------------------------------------------------
const braveKeySet = ref(false)
const showBraveDialog = ref(false)
const braveKeyInput = ref('')
const savingBraveKey = ref(false)
const hasBraveTool = computed(() => tools.value.some((t) => t.name === 'web_search_brave'))

const saveBraveKey = async () => {
  savingBraveKey.value = true
  try {
    braveKeySet.value = await setBraveKey(braveKeyInput.value.trim() || null)
    braveKeyInput.value = ''
    showBraveDialog.value = false
    toast.success(braveKeySet.value ? 'Brave key saved' : 'Brave key cleared')
  } catch {
    toast.error('Could not save the Brave key')
  } finally {
    savingBraveKey.value = false
  }
}

const messages = ref<Msg[]>([])
const input = ref('')
const sending = ref(false)
const bottomAnchor = ref<HTMLElement | null>(null)
let controller: AbortController | null = null

const canSend = computed(() => !!model.value && !sending.value && !!input.value.trim())

const TOOL_ICON: Record<string, unknown> = {
  web_search: Search,
  web_search_brave: Globe,
  generate_image: ImageIcon,
}
const toolIcon = (name: string) => TOOL_ICON[name] ?? Wrench
const toolLabel = (name: string) => name.replace(/_/g, ' ')

// --- scroll stickiness (mirrors the chat playground) ----------------------
const autoScroll = ref(true)
const nearBottom = () => {
  const el = document.documentElement
  return el.scrollHeight - el.scrollTop - el.clientHeight < 120
}
const onScroll = () => { autoScroll.value = nearBottom() }
const scrollDown = async (force = false) => {
  if (!force && !autoScroll.value) return
  await nextTick()
  bottomAnchor.value?.scrollIntoView({ block: 'end' })
  window.scrollTo({ top: document.documentElement.scrollHeight })
}

// --- persistence (reuses ChatThread) --------------------------------------
const serializeMessages = (): StoredMessage[] =>
  messages.value
    .filter((m) => m.role === 'user' || (m.done && !m.error))
    .map((m) => {
      const out: StoredMessage = { role: m.role, content: m.content }
      if (m.reasoning) out.reasoning = m.reasoning
      if (m.usage) out.usage = m.usage
      return out
    })

const persistThread = async () => {
  if (!messages.value.some((m) => m.role === 'assistant' && m.done && !m.error)) return
  const payload = { model: model.value, messages: serializeMessages() }
  try {
    if (!threadId.value) {
      threadId.value = (await createThread(payload)).public_id
    } else {
      await updateThread(threadId.value, payload)
    }
  } catch (e) {
    console.warn('Could not save agent thread', e)
  }
}

const hydrateFromThread = async (publicId: string) => {
  try {
    const t = await getThread(publicId)
    threadId.value = t.public_id
    if (t.model && models.value.some((m) => m.id === t.model)) model.value = t.model
    messages.value = t.messages.map((m) => ({
      role: m.role,
      content: m.content,
      reasoning: m.reasoning || '',
      tools: [],
      usage: m.usage,
      done: true,
    }))
    await scrollDown(true)
  } catch {
    /* a missing/forbidden thread just starts empty */
  }
}

// --- send -----------------------------------------------------------------
const buildMessages = (history: Msg[]) =>
  history
    .filter((m) => m.content.trim() && !m.error)
    .map((m) => ({ role: m.role, content: m.content }))

const send = async () => {
  if (!canSend.value) return
  const text = input.value.trim()
  input.value = ''

  messages.value.push({ role: 'user', content: text, reasoning: '', tools: [], done: true })
  const history = messages.value.slice()
  const assistant = reactive<Msg>({ role: 'assistant', content: '', reasoning: '', tools: [], done: false })
  messages.value.push(assistant)
  sending.value = true
  controller = new AbortController()
  autoScroll.value = true
  await scrollDown(true)

  try {
    await runAgent(
      { model: model.value, messages: buildMessages(history), ...(skill.value ? { skill: skill.value } : {}) },
      {
        signal: controller.signal,
        onToolCall: (call) => {
          assistant.tools.push({ ...call })
          scrollDown()
        },
        onToolResult: (id, ok, summary, data) => {
          const card = assistant.tools.find((c) => c.id === id)
          if (!card) return
          card.ok = ok
          card.summary = summary
          card.done = true
          const media = (data?.media as AgentMedia[] | undefined)
          if (Array.isArray(media) && media.length) card.media = media
          scrollDown()
        },
        onReasoning: (c) => { assistant.reasoning += c; scrollDown() },
        onText: (c) => { assistant.content += c; scrollDown() },
        onUsage: (u) => { assistant.usage = u },
      }
    )
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name === 'AbortError') {
      assistant.content += assistant.content ? '\n\n_(stopped)_' : '_(stopped)_'
    } else {
      assistant.error = true
      assistant.content = err?.message || 'Agent request failed'
    }
  } finally {
    assistant.tools.forEach((c) => { c.done = true })
    assistant.done = true
    sending.value = false
    controller = null
    scrollDown()
    void persistThread()
  }
}

const stop = () => controller?.abort()

const clear = () => {
  if (sending.value) return
  messages.value = []
  threadId.value = null
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  try {
    const meta = await listTools()
    agentEnabled.value = meta.enabled
    tools.value = meta.tools
    skills.value = meta.skills
    braveKeySet.value = meta.braveKeySet
  } catch { /* non-fatal */ }
  try {
    models.value = (await listModels()).filter((m) => m.service_type === 'llm')
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
      const wantedThread = String(useRoute().query.thread || '')
      if (wantedThread) await hydrateFromThread(wantedThread)
    } else {
      modelsError.value = 'No models are available to you right now.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
  if (!agentEnabled.value) {
    modelsError.value = 'The Agent is not enabled on this server.'
  }
})

onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Sparkles class="h-6 w-6" /> Agent
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          A chat assistant that can use tools — search the web and generate images on your behalf.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="ghost" size="sm" as-child>
          <NuxtLink to="/dashboard/playground">Plain chat</NuxtLink>
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="gap-1.5"
          :disabled="!messages.length || sending"
          title="Start a new chat"
          @click="clear"
        >
          <Plus class="size-4" /> New chat
        </Button>
      </div>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ modelsError }}
    </div>

    <!-- Available tools -->
    <div v-if="tools.length" class="mb-4 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <span>Tools:</span>
      <span
        v-for="t in tools"
        :key="t.name"
        class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5"
        :title="t.description"
      >
        <component :is="toolIcon(t.name)" class="size-3" />
        {{ toolLabel(t.name) }}
      </span>
      <button
        v-if="hasBraveTool"
        type="button"
        class="inline-flex items-center gap-1 rounded-full border border-dashed px-2 py-0.5 hover:bg-muted"
        @click="showBraveDialog = true"
      >
        <Key class="size-3" />
        {{ braveKeySet ? 'Brave key set' : 'Add Brave key' }}
      </button>
    </div>

    <!-- Brave key dialog -->
    <Dialog :open="showBraveDialog" @update:open="showBraveDialog = $event">
      <DialogContent class="sm:max-w-md">
        <DialogHeader class="text-left">
          <DialogTitle class="flex items-center gap-2 text-base">
            <Key class="size-4 text-muted-foreground" /> Brave Search API key
          </DialogTitle>
          <DialogDescription class="text-xs">
            Your personal key enables the Brave web-search tool. Stored on your account and never shown again.
          </DialogDescription>
        </DialogHeader>
        <Input
          v-model="braveKeyInput"
          type="password"
          placeholder="BSA…"
          class="text-sm"
          @keydown.enter="saveBraveKey"
        />
        <DialogFooter class="flex-row justify-between gap-2 sm:justify-between">
          <Button
            v-if="braveKeySet"
            variant="ghost"
            size="sm"
            class="text-muted-foreground"
            :disabled="savingBraveKey"
            @click="braveKeyInput = ''; saveBraveKey()"
          >
            Clear key
          </Button>
          <Button size="sm" :disabled="savingBraveKey || !braveKeyInput.trim()" @click="saveBraveKey">
            <Loader2 v-if="savingBraveKey" class="mr-1 size-3.5 animate-spin" /> Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <div class="flex flex-col">
      <div class="flex-1 space-y-4">
        <div
          v-if="!messages.length"
          class="min-h-[35vh] flex flex-col items-center justify-center text-center text-muted-foreground"
        >
          <Bot class="size-10 mb-3 opacity-40" />
          <p class="text-sm">Ask the Agent to research something or create an image.</p>
          <p class="text-xs mt-1">e.g. “Search for the latest on small LLMs, then make a poster image.”</p>
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
            <!-- Reasoning -->
            <details
              v-if="m.reasoning"
              class="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20"
            >
              <summary class="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                Thinking
              </summary>
              <pre class="px-3 pb-2 text-xs whitespace-pre-wrap text-amber-900/80 dark:text-amber-200/70 font-sans">{{ m.reasoning }}</pre>
            </details>

            <!-- Tool-call cards -->
            <div
              v-for="card in m.tools"
              :key="card.id"
              class="rounded-lg border bg-muted/30 text-sm"
            >
              <div class="flex items-center gap-2 px-3 py-2">
                <component :is="toolIcon(card.name)" class="size-4 text-muted-foreground shrink-0" />
                <span class="font-medium">{{ toolLabel(card.name) }}</span>
                <span class="truncate text-xs text-muted-foreground">
                  {{ (card.arguments.query || card.arguments.prompt || '') as string }}
                </span>
                <Loader2 v-if="!card.done" class="ml-auto size-3.5 animate-spin text-muted-foreground" />
                <span v-else-if="card.ok === false" class="ml-auto text-xs text-destructive">failed</span>
              </div>
              <!-- Generated media renders inline -->
              <div v-if="card.media?.length" class="flex flex-wrap gap-2 px-3 pb-3">
                <template v-for="item in card.media" :key="item.id">
                  <img
                    v-if="item.kind === 'image'"
                    :src="item.url"
                    alt="generated image"
                    class="max-h-56 rounded-md border"
                  />
                  <video v-else-if="item.kind === 'video'" :src="item.url" controls class="max-h-56 rounded-md border" />
                  <audio v-else :src="item.url" controls class="w-full" />
                </template>
              </div>
              <details v-else-if="card.done && card.summary" class="px-3 pb-2">
                <summary class="cursor-pointer text-xs text-muted-foreground">Details</summary>
                <pre class="mt-1 text-xs whitespace-pre-wrap text-muted-foreground font-sans">{{ card.summary }}</pre>
              </details>
            </div>

            <!-- Body -->
            <div v-if="m.error" class="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">
              {{ m.content }}
            </div>
            <pre
              v-else-if="m.role === 'user' || (!m.done && !m.content)"
              class="text-sm whitespace-pre-wrap font-sans"
            >{{ m.content || (m.role === 'assistant' && sending && !m.tools.length ? '…' : '') }}</pre>
            <pre v-else-if="!m.done" class="text-sm whitespace-pre-wrap font-sans">{{ m.content }}</pre>
            <MarkdownRenderer v-else :content="m.content" />

            <!-- Footer usage -->
            <div
              v-if="m.done && m.role === 'assistant' && !m.error && m.usage"
              class="flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground"
            >
              <span v-if="m.usage.prompt_tokens != null">↑ {{ m.usage.prompt_tokens }} in</span>
              <span v-if="m.usage.completion_tokens != null">↓ {{ m.usage.completion_tokens }} out</span>
            </div>
          </div>
        </div>
        <div ref="bottomAnchor" />
      </div>

      <!-- Composer -->
      <div class="sticky bottom-0 z-10 bg-gradient-to-t from-background via-background to-transparent pt-4 pb-2">
        <div class="rounded-2xl border bg-background shadow-sm focus-within:ring-1 focus-within:ring-ring transition">
          <textarea
            v-model="input"
            rows="1"
            :placeholder="model ? 'Ask the Agent…' : 'Select a model first'"
            :disabled="!model || !agentEnabled"
            class="w-full resize-none bg-transparent px-4 pt-3 pb-1 text-sm outline-none max-h-48 min-h-[2.5rem]"
            @keydown="onKeydown"
            @input="(e) => { const t = e.target as HTMLTextAreaElement; t.style.height='auto'; t.style.height = Math.min(t.scrollHeight, 192) + 'px' }"
          />
          <div class="flex items-center gap-1.5 px-2.5 pb-2.5">
            <ModelPicker v-model="model" :models="models" :loading="loadingModels" />
            <select
              v-if="skills.length"
              v-model="skill"
              class="h-9 rounded-full border bg-background px-3 text-xs text-muted-foreground outline-none hover:text-foreground"
              title="Pick a skill to focus the agent"
            >
              <option value="">No skill</option>
              <option v-for="s in skills" :key="s.name" :value="s.name">{{ s.title }}</option>
            </select>
            <div class="ml-auto flex items-center gap-1">
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
          The Agent can search the web and generate images. Generated images are saved to your gallery.
        </p>
      </div>
    </div>
  </div>
</template>
