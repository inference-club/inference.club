// Client for the guided "Image → Video" playground. This composable does NOT
// add any new backend surface — it orchestrates three EXISTING OpenAI-style
// endpoints with the logged-in session:
//   1. POST /v1/images/generations  (text → image, asked for as b64_json)
//   2. POST /v1/chat/completions    (vision LLM → structured video prompts)
//   3. POST /v1/videos/generations  (image + prompt → MP4 bytes)
// All requests reuse the same session/CSRF conventions as the other playground
// composables (useImageGeneration / useVideoGeneration / usePlayground).

import type { ModelInfo } from '@/composables/usePlayground'

export interface VisionPromptResult {
  description: string
  prompts: string[]
}

export function useImageToVideo() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  const _headers = () => {
    const token = csrf()
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'X-CSRFToken': token } : {}),
    }
  }

  // All models, mapped to ModelInfo (mirrors usePlayground.listModels). Callers
  // filter by service_type / input_modalities.
  const listModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, { credentials: 'include' })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? []).map((m: Partial<ModelInfo> & { id: string }) => ({
      id: m.id,
      input_modalities: m.input_modalities ?? ['text'],
      supported_features: m.supported_features ?? [],
      context_length: m.context_length ?? null,
      service_type: m.service_type ?? 'llm',
    }))
  }

  // Stage 1 — text → image. We force response_format: "b64_json" so we can keep
  // the result as a data URI (needed as the first frame for stages 2 & 3).
  const generateImage = async (
    opts: { model: string; prompt: string; size?: string },
    signal?: AbortSignal,
  ): Promise<string> => {
    const res = await fetch(`${config.public.apiBase}/v1/images/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: _headers(),
      body: JSON.stringify({
        model: opts.model,
        prompt: opts.prompt,
        ...(opts.size ? { size: opts.size } : {}),
        response_format: 'b64_json',
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const item = (await res.json())?.data?.[0]
    if (item?.b64_json) return `data:image/png;base64,${item.b64_json}`
    if (item?.url) return item.url // fallback: backend returned a URL anyway
    throw new Error('Image endpoint returned no image data')
  }

  const VIDEO_PROMPT_SYSTEM = (count: number, duration: number) =>
    `You are an expert prompt writer for the LTX-2.3 image-to-video model and a sharp comedy writer. You are shown a still image that is the FIRST FRAME of a short ~${duration}s video. Propose ${count} DISTINCT prompts for what happens NEXT — the motion that brings the still to life. Make them interesting, surprising, and genuinely funny.

Follow these LTX-2.3 rules strictly:
- Each prompt is ONE flowing paragraph, present tense. No lists, no line breaks.
- This is image-to-video: do NOT re-describe what is already visible in the frame. Describe the TRANSITION from stillness to motion — how subjects move and how the camera moves.
- Order ideas within the paragraph as: shot/camera framing, then the action, then character beats, then camera movement, then audio.
- If there are people or characters, give them DIALOGUE. Format as: Character (delivery style): "short line." Break long lines into short phrases with PHYSICAL acting cues between them (e.g. he pauses, glances aside, voice cracking). Never use abstract emotion labels like 'sad' or 'excited' — show it physically.
- Describe SOUND concretely: ambient sound, sound effects, and music (e.g. 'the sound of rain on pavement', 'a sudden cartoonish boing', 'soft ambient music', 'a crowd gasps then bursts out laughing'). Use volume words for voices (whisper to shout).
- Use real cinematography terms (slow push-in, dolly in, handheld tracking, close-up, whip pan, low angle, golden hour, shallow depth of field, slow motion).
- Keep it physically plausible. Avoid chaotic physics, on-screen readable text or logos, numeric specs (like degrees/second), and self-contradictions. Make each prompt detailed enough to fill the duration.
- The ${count} options must differ from each other in concept and comedic angle.

Return ONLY valid JSON: an object with 'description' (one sentence on what the image shows) and 'prompts' (an array of ${count} prompt strings).`

  // Stage 2 — vision LLM → { description, prompts }. Sends the first frame as a
  // multimodal image_url and asks for structured JSON via response_format.
  // `avoid` carries already-shown prompts so "Generate more" stays distinct.
  const suggestPrompts = async (
    opts: {
      model: string
      imageDataUri: string
      count: number
      duration: number
      avoid?: string[]
      extra?: string
    },
    signal?: AbortSignal,
  ): Promise<VisionPromptResult> => {
    const { model, imageDataUri, count, duration, avoid = [], extra = '' } = opts
    let userText = `Here is the first frame. Propose ${count} funny video continuations.`
    if (avoid.length) {
      userText += ` Avoid repeating these earlier ideas: ${avoid
        .map((p) => `"${p}"`)
        .join('; ')}. Give ${count} fresh, different ones.`
    }
    if (extra.trim()) userText += ` ${extra.trim()}`

    const body = {
      model,
      messages: [
        // "detailed thinking off" disables the Nemotron reasoning trace — without
        // it, the reasoning model spends the whole token budget thinking and never
        // emits the JSON (content comes back null). Harmless to non-Nemotron models.
        {
          role: 'system',
          content: `detailed thinking off\n${VIDEO_PROMPT_SYSTEM(count, duration)}`,
        },
        {
          role: 'user',
          content: [
            { type: 'text', text: userText },
            { type: 'image_url', image_url: { url: imageDataUri } },
          ],
        },
      ],
      // Each LTX prompt is a long, detailed paragraph; give the N-prompt JSON room
      // so it isn't truncated mid-string (finish_reason: length).
      max_tokens: Math.min(8000, 1500 + count * 1200),
      response_format: {
        type: 'json_schema',
        json_schema: {
          name: 'video_prompts',
          schema: {
            type: 'object',
            properties: {
              description: { type: 'string' },
              prompts: { type: 'array', items: { type: 'string' } },
            },
            required: ['description', 'prompts'],
          },
        },
      },
    }

    const res = await fetch(`${config.public.apiBase}/v1/chat/completions`, {
      method: 'POST',
      credentials: 'include',
      headers: _headers(),
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const data = await res.json()
    const content = data?.choices?.[0]?.message?.content
    if (typeof content !== 'string') throw new Error('The model returned no content')
    let parsed: VisionPromptResult
    try {
      parsed = JSON.parse(content)
    } catch {
      // Some models fence JSON in ```json … ``` — strip and retry once.
      const m = content.match(/\{[\s\S]*\}/)
      if (!m) throw new Error('Could not parse the model response as JSON')
      parsed = JSON.parse(m[0])
    }
    return {
      description: typeof parsed.description === 'string' ? parsed.description : '',
      prompts: Array.isArray(parsed.prompts) ? parsed.prompts.filter((p) => typeof p === 'string') : [],
    }
  }

  // Stage 3 — image + prompt → MP4 bytes. Mirrors useVideoGeneration.generate's
  // exact request shape and binary handling (raw MP4 → object URL).
  const generateVideo = async (
    opts: {
      model: string
      prompt: string
      image: string
      duration?: number
      width?: number
      height?: number
    },
    signal?: AbortSignal,
  ): Promise<{ blob: Blob; url: string; contentType: string }> => {
    const res = await fetch(`${config.public.apiBase}/v1/videos/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: _headers(),
      body: JSON.stringify({
        model: opts.model,
        prompt: opts.prompt,
        image: opts.image,
        image_strength: 1,
        ...(opts.duration ? { duration: opts.duration } : {}),
        ...(opts.width ? { width: opts.width } : {}),
        ...(opts.height ? { height: opts.height } : {}),
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const blob = await res.blob()
    return {
      blob,
      url: URL.createObjectURL(blob),
      contentType: res.headers.get('content-type') || 'video/mp4',
    }
  }

  return { listModels, generateImage, suggestPrompts, generateVideo }
}
