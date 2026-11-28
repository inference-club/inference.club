// What the request detail and share pages show, worked out from one request:
// its name, its prompt, the handful of facts worth a glance (who, where, how
// fast) and the settings that shaped the result. Everything else stays in the
// collapsed "all details" section.

import type { InferenceRequest } from '@/types'
import { formatLatency, totalTokens } from '@/utils/inference'
import { prettyGpuModel } from '@/composables/useMachineForm'

type Payload = Record<string, unknown>

const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : '')
const isSet = (v: unknown): boolean =>
  v !== null && v !== undefined && v !== '' && v !== 'None' && v !== 'null'

/** The words the person gave: prompt, spoken text, or the last thing they said. */
export function requestPrompt(req: InferenceRequest): string {
  const p = (req.payload ?? {}) as Payload
  const direct = str(p.prompt) || str(p.input)
  if (direct && direct !== 'None') return direct
  const users = (req.messages ?? []).filter((m) => m.role === 'user')
  return str(users[users.length - 1]?.content) || str(req.prompt_preview)
}

/** File the person supplied, when the input was a file, not words. */
export function requestSourceName(req: InferenceRequest): string {
  const p = (req.payload ?? {}) as Payload
  return str(p.source_filename) || str(p.filename)
}

/** A name for the page: the saved title, else the start of the prompt. */
export function requestTitle(req: InferenceRequest, fallback: string): string {
  const p = (req.payload ?? {}) as Payload
  const named = str(req.title) || str(p.title)
  if (named) return named
  const words = requestPrompt(req).replace(/\s+/g, ' ')
  if (words) return words.length > 72 ? `${words.slice(0, 70).trimEnd()}…` : words
  return requestSourceName(req) || fallback
}

export interface Fact {
  key: string
  value: string
  /** Smaller second line. */
  hint?: string
  to?: string | null
}

const seconds = (s: number): string => {
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, '0')}`
}

/**
 * The measured facts for the strip under the result, in reading order. Keys
 * are i18n keys under `request.facts`; only facts that exist are returned.
 */
export function requestFacts(req: InferenceRequest, nodeLink: string | null): Fact[] {
  const out: Fact[] = []
  const host = req.host
  const machine = host?.hostname || host?.host_id || req.provider?.name
  if (machine) {
    out.push({
      key: 'machine',
      value: machine,
      hint: req.provider?.name && req.provider.name !== machine ? req.provider.name : undefined,
      to: nodeLink,
    })
  }
  const gpus = host?.gpu ? [host.gpu] : host?.gpus ?? []
  if (gpus.length) {
    const first = gpus[0] as { model?: string | null; vram_gb?: number | null }
    out.push({
      key: 'gpu',
      value: prettyGpuModel(first.model || '') + (gpus.length > 1 ? ` ×${gpus.length}` : ''),
      hint: first.vram_gb ? `${Math.round(first.vram_gb)} GB` : undefined,
      to: nodeLink,
    })
  }
  if (req.model_name) out.push({ key: 'model', value: req.model_name })
  if (req.latency_ms != null) {
    const audio = req.audio_seconds
    // For audio, how much faster than real time it was made is the fun number.
    const speed =
      audio && req.latency_ms > 0 ? audio / (req.latency_ms / 1000) : null
    out.push({
      key: 'took',
      value: formatLatency(req.latency_ms),
      hint: speed && speed >= 1.5 ? `${speed.toFixed(speed < 10 ? 1 : 0)}× real time` : undefined,
    })
  }
  if (req.ttft_ms != null) out.push({ key: 'firstToken', value: formatLatency(req.ttft_ms) })
  if (req.tokens_per_second != null) {
    out.push({ key: 'speed', value: `${Math.round(req.tokens_per_second)} tok/s` })
  }
  const tokens = totalTokens(req)
  if (tokens !== null) {
    out.push({
      key: 'tokens',
      value: tokens.toLocaleString(),
      hint: `${req.usage?.prompt_tokens ?? '?'} → ${req.usage?.completion_tokens ?? '?'}`,
    })
  }
  if (req.audio_seconds != null) out.push({ key: 'length', value: seconds(req.audio_seconds) })
  else if (req.video?.seconds != null) out.push({ key: 'length', value: seconds(req.video.seconds) })
  if (req.video?.width && req.video?.height) {
    out.push({
      key: 'size',
      value: `${req.video.width}×${req.video.height}`,
      hint: req.video.fps != null ? `${req.video.fps} fps` : undefined,
    })
  }
  if (req.inference_type === 'IMAGE') {
    const size = str((req.payload as Payload | undefined)?.size)
    if (size) {
      out.push({
        key: 'size',
        value: size.replace('x', '×'),
        hint: (req.image_count ?? 0) > 1 ? `×${req.image_count}` : undefined,
      })
    }
  }
  if (req.mesh?.faces != null) {
    out.push({
      key: 'mesh',
      value: `${req.mesh.faces.toLocaleString()}`,
      hint: req.mesh.vertices != null ? `${req.mesh.vertices.toLocaleString()} v` : undefined,
    })
  }
  return out
}

export interface Setting {
  /** i18n key under `request.settings`, or the raw parameter name. */
  key: string
  known: boolean
  value: string
}

// Parameters people actually tune, in the order worth reading. Several raw
// names map to one label.
const KNOWN: Array<[label: string, names: string[]]> = [
  ['voice', ['voice']],
  ['language', ['language']],
  ['duration', ['audio_duration', 'duration']],
  ['steps', ['inference_steps', 'num_inference_steps', 'steps']],
  ['guidance', ['guidance_scale', 'cfg_scale']],
  ['seed', ['seed']],
  ['bpm', ['bpm']],
  ['key', ['key_scale']],
  ['temperature', ['temperature']],
  ['topP', ['top_p']],
  ['maxTokens', ['max_tokens', 'max_completion_tokens']],
  ['frames', ['num_frames']],
  ['fps', ['fps']],
  ['count', ['n']],
]

// Shown elsewhere on the page, or plumbing nobody reads.
const HIDDEN = new Set([
  'messages', 'prompt', 'input', 'model', 'title', 'lyrics', 'negative_prompt',
  'size', 'stream', 'tools', 'asset_id', 'input_asset_id', 'size_bytes',
  'content_type', 'response_format', 'audio_format', 'filename',
  'source_filename', 'cover_for', 'use_random_seed', 'agent', 'has_image',
  'inputs', 'stream_options', 'logprobs', 'top_logprobs',
])

const show = (v: unknown): string => {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(+v.toFixed(3))
  if (typeof v === 'boolean') return v ? 'on' : 'off'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** Settings worth showing, and the rest for the collapsed section. */
export function requestSettings(req: InferenceRequest): { main: Setting[]; rest: Setting[] } {
  const p = (req.payload ?? {}) as Payload
  const main: Setting[] = []
  const used = new Set<string>()
  for (const [label, names] of KNOWN) {
    const name = names.find((n) => isSet(p[n]))
    names.forEach((n) => used.add(n))
    if (!name) continue
    // A random seed is not a setting anyone chose.
    if (label === 'seed' && (p[name] === -1 || p[name] === '-1')) continue
    // One result is the default, not a choice.
    if (label === 'count' && Number(p[name]) === 1) continue
    let value = show(p[name])
    if (label === 'duration') value = seconds(Number(p[name]))
    main.push({ key: label, known: true, value })
  }
  const rest: Setting[] = Object.entries(p)
    .filter(([k, v]) => !used.has(k) && !HIDDEN.has(k) && isSet(v))
    .map(([k, v]) => ({ key: k, known: false, value: show(v) }))
  return { main, rest }
}
