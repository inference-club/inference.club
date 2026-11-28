// The assistant: say (or type) what you want and the app does it.
//
// This store drives the panel in components/AssistantPanel.vue. It talks to
// POST /v1/agent with `skill: "assistant"`, which runs the same tools the
// remote MCP server offers (backend/apps/inference/control_tools.py), so the
// panel, Claude, Hermes and the `ic` CLI all do the same things.
//
// A turn streams typed events: tool_call → tool_result (with a one-sentence
// `summary`, optional media, optional job ids and an optional `client_action`
// the app carries out: navigate or play) → the spoken/written answer.

import { defineStore } from 'pinia'
import { usePlayerStore } from '@/stores/player'
import type { PlayerTrack } from '@/utils/player'

export interface AssistantMedia {
  url: string
  kind: string
  content_type?: string
}

export interface AssistantJob {
  id: string
  kind: string
  title?: string
  status: string
  media: AssistantMedia[]
  error?: string
}

export interface AssistantAction {
  id: string
  name: string
  done: boolean
  ok?: boolean
  summary?: string
  media: AssistantMedia[]
  jobs: AssistantJob[]
}

export interface AssistantTurn {
  role: 'user' | 'assistant'
  text: string
  spoken?: boolean
  actions: AssistantAction[]
  done: boolean
  error?: string
}

type Status = 'idle' | 'listening' | 'transcribing' | 'working' | 'speaking'

const TERMINAL = ['PROCESSED', 'FAILED', 'CANCELED']
const HISTORY_LIMIT = 16
const mediaKind = (m: { kind?: string; content_type?: string; url?: string }) => {
  const k = `${m.kind ?? ''} ${m.content_type ?? ''}`.toLowerCase()
  if (k.includes('image')) return 'image'
  if (k.includes('video')) return 'video'
  if (k.includes('audio') || k.includes('music') || k.includes('speech')) return 'audio'
  return 'file'
}

export const useAssistantStore = defineStore('assistant', () => {
  const config = useRuntimeConfig()
  const api = config.public.apiBase

  const open = ref(false)
  const turns = ref<AssistantTurn[]>([])
  const status = ref<Status>('idle')
  const models = ref<string[]>([])
  const model = ref('') // '' = let the server pick
  const speakReplies = ref(false)
  const loaded = ref(false)

  // OpenAI-shape history sent back each turn, so follow-ups ("yes, delete it")
  // see what was said and which tools ran.
  let history: Record<string, unknown>[] = []
  let abort: AbortController | null = null
  let sttModel = ''
  let ttsModel = ''
  let speechAudio: HTMLAudioElement | null = null
  const jobTimers = new Map<string, ReturnType<typeof setTimeout>>()

  const busy = computed(() => status.value === 'working' || status.value === 'transcribing')

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]
  const headers = (json = true): Record<string, string> => {
    const token = csrf()
    return {
      ...(json ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-CSRFToken': token } : {}),
    }
  }

  const load = async () => {
    if (loaded.value || !import.meta.client) return
    loaded.value = true
    model.value = localStorage.getItem('assistant:model') ?? ''
    speakReplies.value = localStorage.getItem('assistant:speak') === '1'
    try {
      const res = await fetch(`${api}/v1/models`, { credentials: 'include' })
      if (!res.ok) return
      const rows: { id: string; service_type?: string; supported_features?: string[] }[] =
        (await res.json()).data ?? []
      models.value = rows.filter((m) => (m.service_type ?? 'llm') === 'llm').map((m) => m.id)
      if (model.value && !models.value.includes(model.value)) model.value = ''
      sttModel = rows.find((m) => m.service_type === 'stt')?.id ?? ''
      const plain = rows.filter(
        (m) =>
          m.service_type === 'tts' &&
          !(m.supported_features ?? []).some((f) => f === 'dialogue' || f === 'voice-cloning'),
      )
      ttsModel = (plain.find((m) => m.id.includes('magpie')) ?? plain[0])?.id ?? ''
    } catch {
      /* the panel still works with the server's default model */
    }
  }

  watch(model, (v) => import.meta.client && localStorage.setItem('assistant:model', v))
  watch(speakReplies, (v) => {
    if (import.meta.client) localStorage.setItem('assistant:speak', v ? '1' : '0')
    if (!v) stopSpeaking()
  })

  const canListen = computed(() => !!sttModel || !loaded.value)

  // --- carrying out what a tool asked the app to do -------------------------

  const runClientAction = (action: Record<string, unknown> | undefined) => {
    if (!action) return
    if (action.type === 'navigate' && typeof action.path === 'string') {
      void navigateTo(action.path)
    } else if (action.type === 'play' && Array.isArray(action.tracks)) {
      const tracks: PlayerTrack[] = (action.tracks as Record<string, unknown>[]).map((t) => ({
        id: String(t.id),
        requestId: String(t.id),
        title: String(t.title || 'Untitled song'),
        url: String(t.url),
        duration: (t.seconds as number) ?? null,
        coverUrl: (t.cover as string) ?? null,
        owner: (t.owner as string) ?? null,
        visibility: (t.visibility as string) ?? null,
      }))
      if (tracks.length) usePlayerStore().playQueue(tracks, 0)
    }
  }

  // --- following queued work until it lands ---------------------------------

  const pollJob = (job: AssistantJob) => {
    const tick = async () => {
      jobTimers.delete(job.id)
      try {
        const res = await fetch(`${api}/v1/jobs/${job.id}`, { credentials: 'include' })
        if (res.ok) {
          const data = await res.json()
          job.status = data.status
          if (data.status === 'PROCESSED') {
            job.media = (data.media ?? []).map((m: AssistantMedia) => ({ ...m, kind: mediaKind(m) }))
          } else if (data.status === 'FAILED') {
            job.error = typeof data.error === 'string' ? data.error : data.error?.message
          }
        }
      } catch {
        /* transient; try again */
      }
      if (!TERMINAL.includes(job.status)) jobTimers.set(job.id, setTimeout(tick, 4000))
    }
    jobTimers.set(job.id, setTimeout(tick, 2500))
  }

  const jobsFrom = (data: Record<string, unknown>): AssistantJob[] => {
    const out: AssistantJob[] = []
    if (Array.isArray(data.jobs)) {
      for (const j of data.jobs as Record<string, unknown>[]) {
        out.push({
          id: String(j.job_id), kind: String(j.kind ?? 'job'),
          title: j.title ? String(j.title) : undefined, status: 'QUEUED', media: [],
        })
      }
    } else if (data.job_id && !TERMINAL.includes(String(data.status))) {
      out.push({
        id: String(data.job_id),
        kind: String(data.inference_type ?? 'job').toLowerCase(),
        status: String(data.status ?? 'QUEUED'),
        media: [],
      })
    }
    return out
  }

  // --- speaking the answer ---------------------------------------------------

  const stopSpeaking = () => {
    speechAudio?.pause()
    speechAudio = null
    if (status.value === 'speaking') status.value = 'idle'
  }

  const speak = async (text: string) => {
    const clean = text.replace(/[*_`#>]/g, '').replace(/https?:\/\/\S+/g, '').trim()
    if (!speakReplies.value || !ttsModel || clean.length < 2) return
    try {
      const res = await fetch(`${api}/v1/audio/speech`, {
        method: 'POST',
        credentials: 'include',
        headers: headers(),
        body: JSON.stringify({ model: ttsModel, input: clean.slice(0, 600), response_format: 'wav' }),
      })
      if (!res.ok) return
      const url = URL.createObjectURL(await res.blob())
      stopSpeaking()
      speechAudio = new Audio(url)
      status.value = 'speaking'
      const finish = () => {
        URL.revokeObjectURL(url)
        if (status.value === 'speaking') status.value = 'idle'
      }
      speechAudio.onended = finish
      speechAudio.onerror = finish
      await speechAudio.play()
    } catch {
      if (status.value === 'speaking') status.value = 'idle'
    }
  }

  // --- one turn ----------------------------------------------------------------

  const context = (spoken: boolean) => {
    const route = useRoute()
    const player = usePlayerStore()
    const item = route.path.match(/\/dashboard\/(?:inference\/requests|watch)\/([\w-]+)/)?.[1]
    return {
      path: route.fullPath,
      ...(item ? { item } : {}),
      ...(player.current
        ? { playing_id: Number(player.current.requestId) || undefined, playing_title: player.current.title }
        : {}),
      ...(spoken ? { spoken: true } : {}),
    }
  }

  const send = async (text: string, opts: { spoken?: boolean } = {}) => {
    const said = text.trim()
    if (!said || busy.value) return
    stopSpeaking()
    await load()
    turns.value.push({ role: 'user', text: said, spoken: opts.spoken, actions: [], done: true })
    turns.value.push({ role: 'assistant', text: '', actions: [], done: false })
    const turn = turns.value[turns.value.length - 1]
    status.value = 'working'
    abort = new AbortController()
    const sent = [...history, { role: 'user', content: said }]

    try {
      const res = await fetch(`${api}/v1/agent`, {
        method: 'POST',
        credentials: 'include',
        headers: headers(),
        body: JSON.stringify({
          skill: 'assistant',
          stream: true,
          messages: sent,
          context: context(!!opts.spoken || speakReplies.value),
          ...(model.value ? { model: model.value } : {}),
        }),
        signal: abort.signal,
      })
      if (!res.ok || !res.body) {
        let message = `HTTP ${res.status}`
        try {
          message = (await res.json())?.error?.message ?? message
        } catch {
          /* keep the status */
        }
        throw new Error(message)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''
        for (const raw of events) {
          const line = raw.split('\n').find((l) => l.startsWith('data:'))
          if (!line) continue
          let ev: Record<string, unknown>
          try {
            ev = JSON.parse(line.slice(5))
          } catch {
            continue
          }
          if (ev.type === 'tool_call') {
            turn.actions.push({ id: String(ev.id), name: String(ev.name), done: false, media: [], jobs: [] })
          } else if (ev.type === 'tool_result') {
            const action = turn.actions.find((a) => a.id === String(ev.id) && !a.done)
            const data = (ev.data as Record<string, unknown>) ?? {}
            if (action) {
              action.done = true
              action.ok = !!ev.ok
              action.summary = String(data.summary ?? ev.summary ?? '').split('\n')[0]
              action.media = ((data.media as AssistantMedia[]) ?? []).map((m) => ({ ...m, kind: mediaKind(m) }))
              action.jobs = jobsFrom(data)
              action.jobs.forEach(pollJob)
            }
            if (ev.ok) runClientAction(data.client_action as Record<string, unknown>)
          } else if (ev.type === 'token') {
            turn.text += String(ev.delta ?? '')
          } else if (ev.type === 'done') {
            history = [...sent, ...((ev.messages as Record<string, unknown>[]) ?? [])].slice(-HISTORY_LIMIT)
            // Never start the history on a tool message without its call.
            while (history.length && history[0].role === 'tool') history.shift()
          } else if (ev.type === 'error') {
            throw new Error(String(ev.message ?? 'The assistant failed.'))
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') turn.error = (e as Error).message
    } finally {
      turn.done = true
      abort = null
      if (status.value === 'working') status.value = 'idle'
    }
    if (!turn.error && turn.text) void speak(turn.text)
  }

  const stop = () => {
    abort?.abort()
    stopSpeaking()
  }

  // --- voice in ------------------------------------------------------------------

  const transcribeAndSend = async (blob: Blob, ext: string) => {
    await load()
    if (!sttModel) {
      turns.value.push({ role: 'assistant', text: '', actions: [], done: true, error: 'no-stt' })
      status.value = 'idle'
      return
    }
    status.value = 'transcribing'
    try {
      const form = new FormData()
      form.append('file', blob, `assistant.${ext}`)
      form.append('model', sttModel)
      const res = await fetch(`${api}/v1/audio/transcriptions`, {
        method: 'POST', credentials: 'include', headers: headers(false), body: form,
      })
      const text = res.ok ? String((await res.json()).text ?? '').trim() : ''
      status.value = 'idle'
      if (text) await send(text, { spoken: true })
    } catch {
      status.value = 'idle'
    }
  }

  const clear = () => {
    stop()
    jobTimers.forEach((t) => clearTimeout(t))
    jobTimers.clear()
    turns.value = []
    history = []
  }

  const toggle = () => {
    open.value = !open.value
    if (open.value) void load()
  }

  return {
    open, turns, status, busy, models, model, speakReplies, canListen,
    load, send, stop, clear, toggle, transcribeAndSend, stopSpeaking,
  }
})
