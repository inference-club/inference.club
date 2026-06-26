// Client for the in-dashboard playground. Talks to the real OpenAI-compatible
// /v1 endpoints using the logged-in session (so no API key to paste), and
// parses streamed SSE responses (content + reasoning + usage).

export interface ChatUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

// One generated token plus its log-probability and the alternatives the model
// weighed. Shape mirrors OpenAI's `choices[].logprobs.content[]` (which vLLM
// emits when the request carries `logprobs: true`).
export interface TokenLogprob {
  token: string
  logprob: number
  top_logprobs?: { token: string; logprob: number }[]
}

export interface StreamCallbacks {
  onText: (chunk: string) => void
  onReasoning: (chunk: string) => void
  onUsage: (usage: ChatUsage) => void
  // Invoked with each batch of per-token logprobs as they arrive (streaming) or
  // once with the full list (non-streaming). Only fires if the request opted in.
  // `kind` says whether these tokens belong to the reasoning trace or the final
  // answer, so the UI can heat-map them in the right place.
  onLogprobs?: (tokens: TokenLogprob[], kind: 'content' | 'reasoning') => void
  signal?: AbortSignal
}

export interface ModelInfo {
  id: string
  input_modalities: string[]
  supported_features: string[]
  context_length: number | null
  // 'llm' | 'stt' | 'tts' — which /v1 surface this model serves. Lets the chat
  // playground hide transcription-only models (and vice versa).
  service_type: string
  // Set for external cloud providers (OpenRouter/NVIDIA/Groq, PRD 19): the
  // picker badges these so it's clear who serves the model. `provider` is the
  // slug, `provider_label` the display name; `display_name` is the friendly
  // model name from the provider catalog.
  external?: boolean
  provider?: string
  provider_label?: string
  display_name?: string
}

export function usePlayground() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const listModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, {
      credentials: 'include',
    })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? []).map((m: Partial<ModelInfo> & { id: string }) => ({
      id: m.id,
      input_modalities: m.input_modalities ?? ['text'],
      supported_features: m.supported_features ?? [],
      context_length: m.context_length ?? null,
      service_type: m.service_type ?? 'llm',
      external: m.external ?? false,
      provider: m.provider,
      provider_label: m.provider_label,
      display_name: m.display_name,
    }))
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Sends a chat completion. For streaming, invokes callbacks as chunks arrive;
  // for non-streaming, invokes them once with the full result.
  const sendChat = async (
    body: Record<string, unknown>,
    cb: StreamCallbacks
  ): Promise<void> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/chat/completions`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify(body),
      signal: cb.signal,
    })

    if (!res.ok) throw new Error(await _errorMessage(res))

    if (!body.stream) {
      const data = await res.json()
      const choice = data?.choices?.[0] ?? {}
      const msg = choice.message ?? {}
      if (msg.content) cb.onText(msg.content)
      const reasoningText: string = msg.reasoning ?? msg.reasoning_content ?? ''
      if (reasoningText) cb.onReasoning(reasoningText)
      const lp = choice.logprobs?.content as TokenLogprob[] | undefined
      if (Array.isArray(lp) && lp.length) {
        // Non-streaming returns one flat token list for the whole generation;
        // split off the leading reasoning tokens by matching the reasoning
        // text's length so the answer heat-map excludes the thinking trace.
        if (reasoningText) {
          const reasoningLp: TokenLogprob[] = []
          const contentLp: TokenLogprob[] = []
          let acc = 0
          for (const t of lp) {
            if (acc < reasoningText.length) {
              reasoningLp.push(t)
              acc += (t.token || '').length
            } else {
              contentLp.push(t)
            }
          }
          if (reasoningLp.length) cb.onLogprobs?.(reasoningLp, 'reasoning')
          if (contentLp.length) cb.onLogprobs?.(contentLp, 'content')
        } else {
          cb.onLogprobs?.(lp, 'content')
        }
      }
      if (data?.usage) cb.onUsage(data.usage)
      return
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response stream')
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE events are separated by a blank line; keep any trailing partial.
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''
      for (const event of events) {
        const dataLine = event.split('\n').find((l) => l.startsWith('data:'))
        if (!dataLine) continue
        const payload = dataLine.slice(5).trim()
        if (!payload || payload === '[DONE]') continue
        let obj: Record<string, unknown>
        try {
          obj = JSON.parse(payload)
        } catch {
          continue
        }
        if (obj.usage) cb.onUsage(obj.usage as ChatUsage)
        const choice = (obj.choices as {
          delta?: Record<string, string>
          logprobs?: { content?: TokenLogprob[] }
        }[] | undefined)?.[0]
        const delta = choice?.delta
        if (delta?.content) cb.onText(delta.content)
        const reasoning = delta?.reasoning ?? delta?.reasoning_content
        if (reasoning) cb.onReasoning(reasoning)
        const lp = choice?.logprobs?.content
        if (lp?.length) {
          // Route this chunk's tokens by the delta field it populated: while the
          // model is thinking it emits reasoning_content, then switches to
          // content for the answer. Keeps the thinking trace out of the main
          // heat-map and into the yellow dropdown.
          const kind = delta?.content ? 'content' : reasoning ? 'reasoning' : 'content'
          cb.onLogprobs?.(lp, kind)
        }
      }
    }
  }

  return { listModels, sendChat }
}
