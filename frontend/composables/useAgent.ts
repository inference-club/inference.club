// Client for the playground Agent (PRD 14). Talks to /v1/agent with the
// logged-in session and parses the agent's typed SSE event stream:
//   tool_call | tool_result | reasoning | token | error | done
// (a small superset of the chat stream usePlayground parses).

import type { ChatUsage } from '@/composables/usePlayground'

export interface AgentMedia {
  id: number
  url: string
  kind: 'image' | 'video' | 'audio'
}

export interface ToolCallEvent {
  id: string
  name: string
  arguments: Record<string, unknown>
  // Filled in once the matching tool_result arrives.
  ok?: boolean
  summary?: string
  data?: Record<string, unknown> | null
  done: boolean
}

export interface AgentTool {
  name: string
  description: string
  full_member_only: boolean
}

export interface AgentSkill {
  name: string
  title: string
  description: string
  tools: string[] | null
}

export interface AgentCallbacks {
  onToolCall: (call: ToolCallEvent) => void
  onToolResult: (id: string, ok: boolean, summary: string, data: Record<string, unknown> | null) => void
  onReasoning: (chunk: string) => void
  onText: (chunk: string) => void
  onUsage: (usage: ChatUsage) => void
  signal?: AbortSignal
}

export function useAgent() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const listTools = async (): Promise<{
    enabled: boolean
    braveKeySet: boolean
    tools: AgentTool[]
    skills: AgentSkill[]
  }> => {
    const res = await fetch(`${config.public.apiBase}/v1/agent/tools`, {
      credentials: 'include',
    })
    if (!res.ok) return { enabled: false, braveKeySet: false, tools: [], skills: [] }
    const data = await res.json()
    return {
      enabled: !!data.enabled,
      braveKeySet: !!data.brave_key_set,
      tools: data.data ?? [],
      skills: data.skills ?? [],
    }
  }

  const setBraveKey = async (apiKey: string | null): Promise<boolean> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/agent/brave-key`, {
      method: apiKey ? 'POST' : 'DELETE',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: apiKey ? JSON.stringify({ api_key: apiKey }) : undefined,
    })
    if (!res.ok) throw new Error('Failed to save key')
    return (await res.json()).brave_key_set
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Runs one agent turn. `messages` is the OpenAI-shape history (incl. the new
  // user turn); `tools` optionally restricts the tool subset. Invokes callbacks
  // as the loop streams tool activity and the final answer.
  const runAgent = async (
    body: { model: string; messages: unknown[]; tools?: string[]; skill?: string },
    cb: AgentCallbacks
  ): Promise<void> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/agent`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({ ...body, stream: true }),
      signal: cb.signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response stream')
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''
      for (const event of events) {
        const dataLine = event.split('\n').find((l) => l.startsWith('data:'))
        if (!dataLine) continue
        const payload = dataLine.slice(5).trim()
        if (!payload) continue
        let obj: Record<string, unknown>
        try {
          obj = JSON.parse(payload)
        } catch {
          continue
        }
        switch (obj.type) {
          case 'tool_call':
            cb.onToolCall({
              id: String(obj.id),
              name: String(obj.name),
              arguments: (obj.arguments as Record<string, unknown>) ?? {},
              done: false,
            })
            break
          case 'tool_result':
            cb.onToolResult(
              String(obj.id),
              !!obj.ok,
              String(obj.summary ?? ''),
              (obj.data as Record<string, unknown>) ?? null
            )
            break
          case 'reasoning':
            cb.onReasoning(String(obj.delta ?? ''))
            break
          case 'token':
            cb.onText(String(obj.delta ?? ''))
            break
          case 'usage':
            cb.onUsage(obj.usage as ChatUsage)
            break
          case 'done':
            if (obj.usage) cb.onUsage(obj.usage as ChatUsage)
            break
          case 'error':
            throw new Error(String(obj.message ?? 'Agent error'))
        }
      }
    }
  }

  return { listTools, setBraveKey, runAgent }
}
