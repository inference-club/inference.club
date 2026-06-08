// "Write with AI" helper for the music playground. Uses any chat (LLM) model on
// the inference.club network to compose song concepts — a music prompt plus
// optional lyrics — which then populate the music-generation form.
//
// The behaviour is driven by an editable *meta-prompt* (the system message).
// We ship a few style presets that each fill the meta-prompt a different way;
// the user can tweak it freely. The model is asked to return a JSON array of
// concepts so we can offer a few variations to choose from.

import type { ModelInfo } from '@/composables/usePlayground'

export interface SongIdea {
  title: string
  prompt: string
  lyrics: string
}

export interface AssistPreset {
  id: string
  label: string
  system: string
}

// Shared output contract — appended to every preset so the model returns
// something we can parse regardless of how the persona is worded.
const FORMAT_RULES = `Respond with ONLY a JSON array — no prose, no markdown code fences. Each element is an object with exactly these keys:
- "title": a short song title (a few words).
- "prompt": one vivid paragraph describing the MUSIC for a text-to-music model — genre, mood, instrumentation, tempo/BPM, and vocal style — written as a comma-separated description.
- "lyrics": the song lyrics using [verse], [chorus], [bridge] section tags, OR an empty string "" for an instrumental.
Make each concept in the array distinct from the others.`

// Style presets. Each one is a complete, editable meta-prompt (persona + style
// guidance + the shared output contract).
export const ASSIST_PRESETS: AssistPreset[] = [
  {
    id: 'balanced',
    label: 'Balanced',
    system: `You are a versatile music director and songwriter creating concepts for an AI music generator. Aim for broad appeal: a clear genre, a singable hook, and a tidy verse/chorus structure.

${FORMAT_RULES}`,
  },
  {
    id: 'cinematic',
    label: 'Cinematic',
    system: `You are a film-score composer and lyricist. Lean atmospheric and emotional: evocative imagery, dynamic builds, and lush orchestration or ambient textures. Keep any lyrics poetic and sparse.

${FORMAT_RULES}`,
  },
  {
    id: 'pop',
    label: 'Pop hooks',
    system: `You are a hit pop songwriter. Write catchy, modern, radio-ready songs: an unforgettable chorus that repeats, bright contemporary production, and an upbeat tempo. Lyrics should be simple and emotionally direct.

${FORMAT_RULES}`,
  },
  {
    id: 'experimental',
    label: 'Experimental',
    system: `You are a boundary-pushing producer. Be bold and unconventional: unexpected genre fusions, unusual time feels and textures, and abstract or surreal lyrics. Surprise the listener.

${FORMAT_RULES}`,
  },
  {
    id: 'instrumental',
    label: 'Instrumental',
    system: `You are an instrumental composer. Every concept is an instrumental — always set "lyrics" to an empty string "". Focus the "prompt" on rich instrumentation, arrangement, dynamics, and mood.

${FORMAT_RULES}`,
  },
]

export function useMusicAssist() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Chat (LLM) models — what can write prompts/lyrics for us.
  const listChatModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, { credentials: 'include' })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? [])
      .map((m: Partial<ModelInfo> & { id: string }) => ({
        id: m.id,
        input_modalities: m.input_modalities ?? ['text'],
        supported_features: m.supported_features ?? [],
        context_length: m.context_length ?? null,
        service_type: m.service_type ?? 'llm',
      }))
      .filter((m: ModelInfo) => m.service_type === 'llm')
  }

  // Pull the first JSON array (or object) out of a model reply, tolerating
  // stray prose or ```json fences some models add despite instructions.
  const _parseIdeas = (content: string): SongIdea[] => {
    let text = content.trim()
    const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
    if (fence) text = fence[1].trim()
    const start = text.indexOf('[')
    const end = text.lastIndexOf(']')
    let raw: unknown
    if (start !== -1 && end > start) {
      raw = JSON.parse(text.slice(start, end + 1))
    } else {
      // Maybe a single object.
      const os = text.indexOf('{')
      const oe = text.lastIndexOf('}')
      if (os === -1 || oe <= os) throw new Error('No JSON found in the model reply')
      raw = JSON.parse(text.slice(os, oe + 1))
    }
    const arr = Array.isArray(raw) ? raw : [raw]
    return arr
      .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
      .map((x) => ({
        title: typeof x.title === 'string' ? x.title : '',
        prompt: typeof x.prompt === 'string' ? x.prompt : '',
        lyrics: typeof x.lyrics === 'string' ? x.lyrics : '',
      }))
      .filter((x) => x.prompt.trim().length > 0)
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Compose `count` song ideas. `system` is the (editable) meta-prompt;
  // `description` is the user's brief — leave it blank for a random surprise.
  const composeIdeas = async (
    opts: { model: string; system: string; description?: string; count?: number },
    signal?: AbortSignal,
  ): Promise<SongIdea[]> => {
    const count = opts.count ?? 3
    const brief = (opts.description ?? '').trim()
    const user = brief
      ? `Generate exactly ${count} distinct song concepts based on this brief:\n\n"${brief}"\n\nReturn ONLY the JSON array.`
      : `Generate exactly ${count} distinct, varied, surprising song concepts across different genres and moods.\n\nReturn ONLY the JSON array.`

    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/chat/completions`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model: opts.model,
        messages: [
          { role: 'system', content: opts.system },
          { role: 'user', content: user },
        ],
        stream: false,
        temperature: 1,
        max_tokens: 1800,
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const data = await res.json()
    const content: string = data?.choices?.[0]?.message?.content ?? ''
    if (!content.trim()) throw new Error('The model returned an empty reply')
    const ideas = _parseIdeas(content)
    if (!ideas.length) throw new Error("Couldn't parse song ideas from the model reply")
    return ideas
  }

  return { listChatModels, composeIdeas }
}
