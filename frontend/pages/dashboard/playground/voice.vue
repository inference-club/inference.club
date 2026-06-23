<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Mic, Settings2, Square, Wand2, Volume2, Bot, User, Search, Globe, Image as ImageIcon, Wrench, Play, Pause, Plus, History } from 'lucide-vue-next'
import { useAgent, type AgentMedia, type ToolCallEvent } from '@/composables/useAgent'
import { useTranscription } from '@/composables/useTranscription'
import { useTextToSpeech } from '@/composables/useTextToSpeech'
import { useAudioRecorder } from '@/composables/useAudioRecorder'
import { usePlayground, type ModelInfo } from '@/composables/usePlayground'
import { useChatThreads, type StoredMessage } from '@/composables/useChatThreads'
import { useConversationPlayer } from '@/composables/useConversationPlayer'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.voiceAgent' })

// ── models ──────────────────────────────────────────────────────────────────
const { listModels } = usePlayground()
const { runAgent } = useAgent()
const { transcribe } = useTranscription()
const { listVoices, synthesize } = useTextToSpeech()
const recorder = useAudioRecorder()
const { createThread, updateThread, getThread } = useChatThreads()

// The saved voice session this conversation persists to (null until the first
// reply lands; reset by "New"). Listed + resumable from /dashboard/chats.
const threadId = ref<string | null>(null)

const llmModels = ref<ModelInfo[]>([])
const sttModels = ref<ModelInfo[]>([])
const ttsModels = ref<ModelInfo[]>([])
const voices = ref<string[]>([])

const llmModel = ref('')
const sttModel = ref('')
const ttsModel = ref('')
const voice = ref('')
// Narration playback speed (HTMLAudioElement.playbackRate; pitch is preserved).
const playbackRate = ref(1)

// Replay player for completed turns (per-message + call-style play-all). The
// live reply is still spoken by the synth pipeline below; this is for re-listen.
const player = useConversationPlayer({ rate: playbackRate })

const loadingModels = ref(true)
const setupError = ref('')
const showSettings = ref(false)

// ── conversation ─────────────────────────────────────────────────────────────
// A tool invocation in a turn: the call (name + args) plus its result once it
// lands (ok/summary, and any generated media to render inline).
type ToolCard = ToolCallEvent & { media?: AgentMedia[] }
interface Turn {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  tools?: ToolCard[]
  // Ordered audio clips: a user turn has its mic recording; an assistant turn
  // has one clip per spoken paragraph. `url` is the durable MediaAsset route.
  audio?: { id?: number; url: string }[]
  done: boolean
  error?: boolean
}
const turns = ref<Turn[]>([])
const transcript = computed(() => turns.value) // alias for template clarity

// Icon + label for a tool trace card (mirrors the text agent).
const TOOL_ICON: Record<string, unknown> = {
  web_search: Search,
  web_search_brave: Globe,
  generate_image: ImageIcon,
  generate_voice: Volume2,
  generate_music: Volume2,
}
const toolIcon = (name: string) => TOOL_ICON[name] ?? Wrench
const toolLabel = (name: string) => name.replace(/_/g, ' ')

// High-level status drives the button + hint text.
type Status = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking'
const status = ref<Status>('idle')
const busy = computed(() => status.value === 'transcribing' || status.value === 'thinking')

// ── mic capture (hold-to-talk OR tap-to-lock) ────────────────────────────────
const TAP_MS = 400
let recordPromise: Promise<{ blob: Blob; ext: string }> | null = null
let pressStart = 0
const locked = ref(false) // a tap started a hands-free, locked listen

const beginRecording = async () => {
  if (recorder.recording.value) return
  try {
    recordPromise = recorder.start()
    status.value = 'listening'
  } catch {
    toast.error('Microphone access was denied')
    status.value = 'idle'
  }
}

const endRecordingAndSend = async () => {
  if (!recorder.recording.value || !recordPromise) return
  recorder.stop()
  const audio = await recordPromise
  recordPromise = null
  locked.value = false
  if (!audio.blob.size) {
    status.value = 'idle'
    return
  }
  await handleUtterance(audio.blob, audio.ext)
}

// Pointer handling: a quick tap toggles a locked listen; a press-and-hold
// records only while held. Any press first barges in on playback.
const onPressDown = async () => {
  if (status.value === 'speaking') stopSpeaking()
  player.stop() // interrupt any replay when the user starts talking
  if (busy.value) return
  if (locked.value) return // the matching tap-up will stop+send
  pressStart = performance.now()
  await beginRecording()
}
const onPressUp = async () => {
  if (busy.value) return
  if (locked.value) {
    await endRecordingAndSend()
    return
  }
  if (!recorder.recording.value) return
  const held = performance.now() - pressStart
  if (held < TAP_MS) {
    locked.value = true // keep listening hands-free until the next tap
  } else {
    await endRecordingAndSend()
  }
}

// ── the voice loop: transcribe → agent (stream) → per-paragraph TTS ───────────
let controller: AbortController | null = null

const handleUtterance = async (blob: Blob, ext: string) => {
  status.value = 'transcribing'
  let text = ''
  let userAudio: { id?: number; url: string }[] | undefined
  try {
    const r = await transcribe(blob, `speech.${ext}`, { model: sttModel.value })
    text = (r.text || '').trim()
    if (r.audioUrl) userAudio = [{ id: r.audioAssetId, url: r.audioUrl }]
  } catch (e) {
    toast.error((e as Error)?.message || 'Transcription failed')
    status.value = 'idle'
    return
  }
  if (!text) {
    toast.message("Didn't catch that — try again.")
    status.value = 'idle'
    return
  }

  turns.value.push({
    role: 'user',
    content: text,
    done: true,
    ...(userAudio ? { audio: userAudio } : {}),
  })
  const assistant = reactive<Turn>({ role: 'assistant', content: '', reasoning: '', tools: [], done: false })
  turns.value.push(assistant)
  status.value = 'thinking'

  // Build OpenAI history. The voice system prompt is server-owned (skill:'voice'),
  // so we send no system message here.
  const history = turns.value
    .filter((t) => t.done || t === assistant)
    .filter((t) => !(t === assistant))
    .map((t) => ({ role: t.role, content: t.content }))

  resetSpeech()
  controller = new AbortController()
  try {
    await runAgent(
      { model: llmModel.value, messages: history, skill: 'voice' },
      {
        onToolCall: (call) => {
          assistant.tools = assistant.tools || []
          assistant.tools.push(call)
        },
        onToolResult: (id, ok, summary, data) => {
          const c = assistant.tools?.find((t) => t.id === id)
          if (c) {
            c.ok = ok
            c.summary = summary
            c.done = true
            const media = data?.media as AgentMedia[] | undefined
            if (Array.isArray(media) && media.length) c.media = media
          }
        },
        onReasoning: (chunk) => {
          assistant.reasoning = (assistant.reasoning || '') + chunk
        },
        onText: (chunk) => {
          assistant.content += chunk
          // Speak completed paragraphs as soon as they arrive — don't wait for
          // the full reply, and never block the text display on narration.
          flushSpeakable(assistant)
        },
        onUsage: () => {},
        signal: controller.signal,
      },
    )
    // Speak whatever paragraph tail is left once the reply is complete.
    flushSpeakable(assistant, true)
  } catch (e) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') {
      assistant.error = true
      assistant.content = assistant.content || err?.message || 'Agent request failed'
    }
  } finally {
    assistant.done = true
    controller = null
    // Save the session (create on first reply, else update). The synth-drain
    // hook persists again once audio clips finish, so this is the text snapshot.
    void persistThread()
    // If nothing is queued/playing, we're back to idle; otherwise the audio
    // playback loop flips us to idle when the last clip ends.
    if (!speaking.synthQueue.length && !speaking.audioQueue.length && !speaking.playing) {
      status.value = 'idle'
    }
  }
}

// ── session persistence + replay ──────────────────────────────────────────────
// Serialize completed turns to the stored shape (text + audio clips + reasoning
// + tool traces). Skips the in-flight assistant turn and any errored turn.
const serializeTurns = (): StoredMessage[] =>
  turns.value
    .filter((t) => t.done && !t.error)
    .map((t) => {
      const out: StoredMessage = { role: t.role, content: t.content }
      if (t.reasoning) out.reasoning = t.reasoning
      if (t.audio?.length) out.audio = t.audio.map((a) => ({ id: a.id ?? 0, url: a.url }))
      if (t.tools?.length) {
        out.tools = t.tools.map((c) => ({
          name: c.name,
          arguments: c.arguments,
          ok: c.ok,
          summary: c.summary,
          ...(c.media?.length ? { media: c.media } : {}),
        }))
      }
      return out
    })

const persistThread = async () => {
  if (!turns.value.some((t) => t.role === 'assistant' && t.done && !t.error)) return
  const payload = { source: 'voice' as const, model: llmModel.value, messages: serializeTurns() }
  try {
    if (!threadId.value) {
      threadId.value = (await createThread(payload)).public_id
    } else {
      await updateThread(threadId.value, payload)
    }
  } catch (e) {
    console.warn('Could not save voice session', e)
  }
}

// Resume a saved voice session (?thread= deep link from /dashboard/chats).
const hydrateFromThread = async (publicId: string) => {
  try {
    const t = await getThread(publicId)
    threadId.value = t.public_id
    if (t.model && llmModels.value.some((m) => m.id === t.model)) llmModel.value = t.model
    turns.value = t.messages.map((m) => ({
      role: m.role,
      content: m.content,
      reasoning: m.reasoning || '',
      tools: (m.tools || []).map((c) => ({
        id: c.name, name: c.name, arguments: c.arguments || {},
        ok: c.ok, summary: c.summary, media: c.media as AgentMedia[] | undefined, done: true,
      })),
      audio: m.audio,
      done: true,
    }))
  } catch {
    /* a missing/forbidden session just starts an empty page */
  }
}

// ── replay controls (per-message + call-style play-all) ───────────────────────
const playMessage = (i: number) => {
  stopSpeaking() // don't fight the live synth pipeline
  if (player.activeMsg.value === i && player.playing.value && !player.paused.value) {
    player.pause()
  } else if (player.activeMsg.value === i && player.paused.value) {
    player.resume()
  } else {
    void player.playOne(turns.value, i)
  }
}
const playAll = () => {
  stopSpeaking()
  void player.playFrom(turns.value, 0)
}
const hasAnyAudio = computed(() => turns.value.some((t) => t.audio?.length))

// ── speech pipeline ──────────────────────────────────────────────────────────
// Two cooperating queues: text segments waiting to synthesize, and synthesized
// audio URLs waiting to play. Synthesis runs ahead of playback so the next clip
// is usually ready by the time the current one finishes.
const speaking = reactive({
  spokenUpTo: 0, // chars of assistant.content already dispatched to TTS
  synthQueue: [] as { text: string; turn: Turn }[],
  audioQueue: [] as string[],
  synthRunning: false,
  playing: false,
})
let speechAbort: AbortController | null = null
let audioEl: HTMLAudioElement | null = null

const resetSpeech = () => {
  speaking.spokenUpTo = 0
  speaking.synthQueue = []
  speaking.audioQueue = []
}

// Pull any *complete* speakable segments out of the streamed text and enqueue
// them. A segment is a paragraph (split on a blank line); on `force` (reply
// finished) the remaining tail is taken even without a trailing blank line. To
// start audio sooner, the first segment may be flushed at a sentence boundary.
const SENTENCE_RE = /[.!?](?:\s|$)/g
const flushSpeakable = (assistant: Turn, force = false) => {
  let pending = assistant.content.slice(speaking.spokenUpTo)
  // Paragraph-complete segments (blank-line separated).
  let nl = pending.indexOf('\n\n')
  while (nl !== -1) {
    const seg = pending.slice(0, nl).trim()
    if (seg) enqueueSpeech(seg, assistant)
    speaking.spokenUpTo += nl + 2
    pending = assistant.content.slice(speaking.spokenUpTo)
    nl = pending.indexOf('\n\n')
  }
  // Early first-audio: if nothing has been spoken yet and a sentence is ready,
  // flush up to the last sentence boundary so playback can start mid-paragraph.
  if (!force && speaking.audioQueue.length === 0 && !speaking.synthQueue.length) {
    SENTENCE_RE.lastIndex = 0
    let lastEnd = -1
    let m: RegExpExecArray | null
    while ((m = SENTENCE_RE.exec(pending))) lastEnd = m.index + 1
    if (lastEnd > 0 && pending.slice(0, lastEnd).trim().length >= 12) {
      const seg = pending.slice(0, lastEnd).trim()
      enqueueSpeech(seg, assistant)
      speaking.spokenUpTo += lastEnd
    }
  }
  if (force) {
    const tail = assistant.content.slice(speaking.spokenUpTo).trim()
    if (tail) {
      enqueueSpeech(tail)
      speaking.spokenUpTo = assistant.content.length
    }
  }
}

// Light text conditioning for the speech model: normalize smart punctuation to
// ASCII so contractions and quotes are pronounced correctly (e.g. the model
// mishandles "Here’s" with a curly apostrophe — make it "Here's"). Applied only
// to the TTS input; the on-screen text keeps its original typography.
const cleanForSpeech = (text: string): string =>
  text
    .replace(/[‘’‚‛′‵]/g, "'") // ‘ ’ ‚ ‛ ′ ‵ → '
    .replace(/[“”„‟″‶]/g, '"') // “ ” „ ‟ ″ ‶ → "

const enqueueSpeech = (text: string, turn: Turn) => {
  if (!ttsModel.value) return // no TTS available — text-only fallback
  // Guard: the Magpie build only speaks Latin-script text. Characters it can't
  // map (e.g. CJK) are dropped, and if too little speakable text remains the
  // model's TRT-LLM executor crashes (fatal "encoder output len" assertion).
  // Skip segments without enough speakable content — the text still displays.
  const speakable = (text.match(/[A-Za-z0-9]/g) || []).length
  if (speakable < 2) return
  speaking.synthQueue.push({ text, turn })
  void runSynthLoop()
}

const runSynthLoop = async () => {
  if (speaking.synthRunning) return
  speaking.synthRunning = true
  speechAbort = speechAbort || new AbortController()
  try {
    while (speaking.synthQueue.length) {
      const { text, turn } = speaking.synthQueue.shift() as { text: string; turn: Turn }
      try {
        const audio = await synthesize(
          // wav (LINEAR_PCM) — the Magpie NIM build rejects ogg/opus ("invalid
          // encoding"); WAV also decodes instantly in the browser (low latency).
          { model: ttsModel.value, input: cleanForSpeech(text), voice: voice.value || undefined, response_format: 'wav' },
          speechAbort.signal,
        )
        // Record the durable asset handle on the turn so the reply can be saved
        // + replayed; fall back to the object URL if the header was absent.
        if (audio.assetUrl) {
          turn.audio = turn.audio || []
          turn.audio.push({ id: audio.assetId, url: audio.assetUrl })
        }
        speaking.audioQueue.push(audio.url)
        playNext()
      } catch (e) {
        if ((e as Error)?.name === 'AbortError') break
        // Skip a failed segment but keep going.
        console.warn('TTS failed for a segment', e)
      }
    }
  } finally {
    speaking.synthRunning = false
    // Synthesis drained: if the reply is finished, the turn's audio clips are
    // now complete — persist the session so it's saved + replayable.
    if (!controller && !speaking.synthQueue.length) void persistThread()
  }
}

const playNext = () => {
  if (speaking.playing || !speaking.audioQueue.length) return
  const url = speaking.audioQueue.shift() as string
  speaking.playing = true
  status.value = 'speaking'
  audioEl = new Audio(url)
  audioEl.playbackRate = playbackRate.value
  audioEl.onended = () => {
    URL.revokeObjectURL(url)
    speaking.playing = false
    audioEl = null
    if (speaking.audioQueue.length) {
      playNext()
    } else if (!speaking.synthRunning && !speaking.synthQueue.length) {
      if (status.value === 'speaking') status.value = 'idle'
    }
  }
  audioEl.onerror = () => {
    URL.revokeObjectURL(url)
    speaking.playing = false
    audioEl = null
    playNext()
  }
  void audioEl.play().catch(() => {
    speaking.playing = false
    playNext()
  })
}

// Apply a speed change to the clip that's already playing, not just the next one.
watch(playbackRate, (r) => {
  if (audioEl) audioEl.playbackRate = r
})

const stopSpeaking = () => {
  speechAbort?.abort()
  speechAbort = null
  if (audioEl) {
    audioEl.pause()
    audioEl.onended = null
    audioEl = null
  }
  speaking.audioQueue.forEach((u) => URL.revokeObjectURL(u))
  speaking.synthQueue = []
  speaking.audioQueue = []
  speaking.playing = false
  speaking.synthRunning = false
  if (status.value === 'speaking') status.value = 'idle'
}

const stopAll = () => {
  controller?.abort()
  controller = null
  if (recorder.recording.value) recorder.stop()
  recordPromise = null
  locked.value = false
  stopSpeaking()
  status.value = 'idle'
}

// ── lifecycle ────────────────────────────────────────────────────────────────
const hint = computed(() => {
  switch (status.value) {
    case 'listening':
      return locked.value ? 'Listening… tap to send' : 'Listening… release to send'
    case 'transcribing':
      return 'Transcribing…'
    case 'thinking':
      return 'Thinking…'
    case 'speaking':
      return 'Speaking… tap to interrupt'
    default:
      return ttsModel.value
        ? 'Hold to talk, or tap to lock hands-free'
        : 'Hold to talk (no voice output available — replies are text only)'
  }
})

// Default to a model id matching one of `prefer` (substring, case-insensitive),
// else the first available. Lets us steer defaults to the right backend without
// hard-failing if it's absent.
const pickDefault = (models: ModelInfo[], prefer: string[]): string => {
  for (const p of prefer) {
    const hit = models.find((m) => m.id.toLowerCase().includes(p))
    if (hit) return hit.id
  }
  return models[0]?.id || ''
}

onMounted(async () => {
  try {
    // One /v1/models call; split by service_type client-side (cheaper than three
    // separate round trips that each re-probe providers server-side).
    const all = await listModels()
    llmModels.value = all.filter((m) => m.service_type === 'llm')
    sttModels.value = all.filter((m) => m.service_type === 'stt')
    // Exclude voice-cloning models (e.g. Dia) — they read text in a *cloned*
    // voice from a reference clip, not what we want for plain narration.
    ttsModels.value = all.filter(
      (m) => m.service_type === 'tts' && !(m.supported_features || []).includes('voice-cloning'),
    )
    // Prefer Nemotron Omni: a vLLM reasoning model whose thinking is returned
    // as separate reasoning_content (kept out of the spoken text) and which
    // streams + tool-calls cleanly — ideal for the voice loop.
    llmModel.value = pickDefault(llmModels.value, ['nemotron'])
    // Prefer the streaming ASR and the general Magpie TTS, which are the
    // backends actually serving these modalities.
    sttModel.value = pickDefault(sttModels.value, ['nemotron', 'streaming'])
    ttsModel.value = pickDefault(ttsModels.value, ['magpie'])
    if (!llmModel.value) setupError.value = 'No chat model is available to you right now.'
    else if (!sttModel.value)
      setupError.value =
        'No speech-to-text model is available. Run an STT agent (a service with type: stt) to enable voice input.'
    // The page is usable now (mic enables). Voices are only needed for the voice
    // picker, so load the (large) list afterward without blocking readiness.
    loadingModels.value = false
    // Resume a saved voice session if deep-linked from /dashboard/chats.
    const wantedThread = String(useRoute().query.thread || '')
    if (wantedThread) await hydrateFromThread(wantedThread)
    if (ttsModel.value) {
      voices.value = await listVoices(ttsModel.value)
      voice.value = pickVoice(voices.value)
    }
  } catch (e) {
    setupError.value = (e as Error)?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
})

// Start a fresh session (only when idle, so we don't orphan an in-flight reply).
const newSession = () => {
  if (busy.value || status.value === 'listening') return
  stopAll()
  player.stop()
  turns.value = []
  threadId.value = null
}

onBeforeUnmount(() => {
  stopAll()
  player.dispose()
})

// Magpie lists ~450 voices across many locales/emotions; default to a plain
// English voice (e.g. EN-US.Aria) rather than whatever sorts first (German).
const pickVoice = (vs: string[]): string => {
  const enBase = vs.find((v) => v.includes('EN-US') && v.split('.').length === 3)
  return enBase || vs.find((v) => v.includes('EN-US')) || vs[0] || ''
}

const onTtsModelChange = async () => {
  voices.value = ttsModel.value ? await listVoices(ttsModel.value) : []
  voice.value = pickVoice(voices.value)
}
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 sm:px-6 py-6 flex flex-col min-h-[calc(100vh-8rem)]">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Volume2 class="h-6 w-6" /> Voice Agent
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Hands-free voice chat — speak, and the agent replies out loud.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-if="hasAnyAudio"
          variant="ghost"
          size="sm"
          class="gap-1.5"
          :title="player.playing.value ? 'Stop playback' : 'Play the whole conversation'"
          @click="player.playing.value ? player.stop() : playAll()"
        >
          <Square v-if="player.playing.value" class="size-4" />
          <Play v-else class="size-4" /> Play all
        </Button>
        <Button variant="ghost" size="sm" class="gap-1.5" as-child title="Saved sessions">
          <NuxtLink to="/dashboard/chats"><History class="size-4" /> History</NuxtLink>
        </Button>
        <Button variant="ghost" size="sm" class="gap-1.5" as-child title="Switch to the text agent">
          <NuxtLink to="/dashboard/playground/agent">
            <Wand2 class="size-4" /> Text agent
          </NuxtLink>
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="gap-1.5"
          :disabled="!transcript.length || busy || status === 'listening'"
          title="Start a new session"
          @click="newSession"
        >
          <Plus class="size-4" /> New
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="gap-1.5"
          :aria-pressed="showSettings"
          @click="showSettings = !showSettings"
        >
          <Settings2 class="size-4" /> Settings
        </Button>
      </div>
    </div>

    <div v-if="setupError" class="p-3 mb-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ setupError }}
    </div>

    <!-- Settings -->
    <div v-if="showSettings" class="mb-4 rounded-lg border p-4 space-y-3">
      <div class="grid sm:grid-cols-2 gap-3">
        <div class="space-y-1">
          <label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Chat model</label>
          <ModelPicker v-model="llmModel" :models="llmModels" :loading="loadingModels" />
        </div>
        <div class="space-y-1">
          <label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Speech-to-text</label>
          <select v-model="sttModel" class="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option v-for="m in sttModels" :key="m.id" :value="m.id">{{ m.id }}</option>
          </select>
        </div>
        <div class="space-y-1">
          <label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Text-to-speech</label>
          <select
            v-model="ttsModel"
            class="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            @change="onTtsModelChange"
          >
            <option value="">None (text only)</option>
            <option v-for="m in ttsModels" :key="m.id" :value="m.id">{{ m.id }}</option>
          </select>
        </div>
        <div v-if="voices.length" class="space-y-1">
          <label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Voice</label>
          <select v-model="voice" class="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option v-for="v in voices" :key="v" :value="v">{{ v }}</option>
          </select>
        </div>
        <div class="space-y-1">
          <label class="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Speech speed</span>
            <span class="tabular-nums normal-case font-normal text-foreground">{{ playbackRate.toFixed(2) }}×</span>
          </label>
          <input
            v-model.number="playbackRate"
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            class="w-full accent-primary"
          />
        </div>
      </div>
      <p class="mt-3 text-xs text-muted-foreground">
        Tools like web search use your
        <NuxtLink to="/dashboard/settings/api-keys" class="text-primary hover:underline">external API keys</NuxtLink>
        — set once, shared with every agent.
      </p>
    </div>

    <!-- Conversation -->
    <div class="flex-1 space-y-4 overflow-y-auto">
      <div
        v-if="!transcript.length"
        class="min-h-[30vh] flex flex-col items-center justify-center text-center text-muted-foreground"
      >
        <Mic class="size-10 mb-3 opacity-40" />
        <p class="text-sm">Press the button below and start talking.</p>
      </div>

      <div v-for="(t, i) in transcript" :key="i" class="flex gap-3">
        <div
          class="size-8 shrink-0 rounded-full flex items-center justify-center"
          :class="t.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'"
        >
          <User v-if="t.role === 'user'" class="size-4" />
          <Bot v-else class="size-4" />
        </div>
        <div class="min-w-0 flex-1 pt-1 space-y-2">
          <!-- Reasoning trace (the model's thinking; streams live, not spoken) -->
          <details v-if="t.reasoning" class="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20" open>
            <summary class="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">Thinking</summary>
            <pre class="px-3 pb-2 text-xs whitespace-pre-wrap text-amber-900/80 dark:text-amber-200/70 font-sans">{{ t.reasoning }}</pre>
          </details>

          <!-- Tool-call trace cards (name + args, result details, inline media) -->
          <div v-for="c in t.tools" :key="c.id" class="rounded-lg border bg-muted/30 text-sm">
            <div class="flex items-center gap-2 px-3 py-2">
              <component :is="toolIcon(c.name)" class="size-4 text-muted-foreground shrink-0" />
              <span class="font-medium">{{ toolLabel(c.name) }}</span>
              <span class="truncate text-xs text-muted-foreground">
                {{ (c.arguments.query || c.arguments.prompt || c.arguments.input || '') as string }}
              </span>
              <Loader2 v-if="!c.done" class="ml-auto size-3.5 animate-spin text-muted-foreground" />
              <span v-else-if="c.ok === false" class="ml-auto text-xs text-destructive">failed</span>
            </div>
            <!-- Generated media renders inline -->
            <div v-if="c.media?.length" class="flex flex-wrap gap-2 px-3 pb-3">
              <template v-for="item in c.media" :key="item.id">
                <img v-if="item.kind === 'image'" :src="item.url" alt="generated image" class="max-h-56 rounded-md border" />
                <video v-else-if="item.kind === 'video'" :src="item.url" controls class="max-h-56 rounded-md border" />
                <audio v-else :src="item.url" controls class="w-full" />
              </template>
            </div>
            <details v-else-if="c.done && c.summary" class="px-3 pb-2">
              <summary class="cursor-pointer text-xs text-muted-foreground">Details</summary>
              <pre class="mt-1 text-xs whitespace-pre-wrap text-muted-foreground font-sans">{{ c.summary }}</pre>
            </details>
          </div>
          <!-- Body + per-message replay -->
          <div v-if="t.error" class="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{{ t.content }}</div>
          <div v-else class="flex items-start gap-2">
            <button
              v-if="t.audio?.length"
              type="button"
              class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border text-muted-foreground hover:text-foreground transition"
              :class="player.activeMsg.value === i && player.playing.value && !player.paused.value ? 'bg-primary text-primary-foreground border-transparent' : ''"
              :title="player.activeMsg.value === i ? 'Pause' : 'Play this message'"
              @click="playMessage(i)"
            >
              <Pause v-if="player.activeMsg.value === i && player.playing.value && !player.paused.value" class="size-3.5" />
              <Play v-else class="size-3.5" />
            </button>
            <pre class="flex-1 text-sm whitespace-pre-wrap font-sans">{{ t.content || (t.role === 'assistant' && !t.done ? '…' : '') }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Mic control -->
    <div class="sticky bottom-0 pt-6 pb-4 flex flex-col items-center gap-3 bg-gradient-to-t from-background via-background to-transparent">
      <button
        type="button"
        class="relative grid place-items-center rounded-full size-24 sm:size-28 transition select-none touch-none focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        :class="[
          status === 'listening' ? 'bg-red-500 text-white scale-105 shadow-lg shadow-red-500/30' : 'bg-primary text-primary-foreground hover:scale-105',
          (status === 'listening' || locked) ? 'animate-pulse' : '',
        ]"
        :disabled="busy || loadingModels || !sttModel || !llmModel"
        :title="hint"
        @pointerdown.prevent="onPressDown"
        @pointerup.prevent="onPressUp"
        @pointerleave="onPressUp"
        @pointercancel="onPressUp"
      >
        <Loader2 v-if="busy" class="size-10 animate-spin" />
        <Volume2 v-else-if="status === 'speaking'" class="size-10" />
        <Mic v-else class="size-10" />
      </button>

      <p class="text-xs text-muted-foreground text-center min-h-[1rem]">{{ hint }}</p>

      <Button
        v-if="status === 'speaking' || status === 'thinking' || locked"
        variant="outline"
        size="sm"
        class="gap-1.5"
        @click="stopAll"
      >
        <Square class="size-3.5" /> Stop
      </Button>
    </div>
  </div>
</template>
