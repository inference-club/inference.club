// Client for the in-dashboard playground. Talks to the real OpenAI-compatible
// /v1 endpoints using the logged-in session (so no API key to paste), and
// parses streamed SSE responses (content + reasoning + usage).

export interface ChatUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export interface StreamCallbacks {
  onText: (chunk: string) => void
  onReasoning: (chunk: string) => void
  onUsage: (usage: ChatUsage) => void
  signal?: AbortSignal
}

export function usePlayground() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const listModels = async (): Promise<string[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, {
      credentials: 'include',
    })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? []).map((m: { id: string }) => m.id)
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
      const msg = data?.choices?.[0]?.message ?? {}
      if (msg.content) cb.onText(msg.content)
      if (msg.reasoning) cb.onReasoning(msg.reasoning)
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
        const delta = (obj.choices as { delta?: Record<string, string> }[] | undefined)?.[0]?.delta
        if (delta?.content) cb.onText(delta.content)
        const reasoning = delta?.reasoning ?? delta?.reasoning_content
        if (reasoning) cb.onReasoning(reasoning)
      }
    }
  }

  return { listModels, sendChat }
}
