import type { InferenceRequest, InferenceStatus } from '@/types'

// Badge variant for a request status. PROCESSED is the happy path; REQUESTED
// is the terminal state the proxy leaves a request in when the upstream call
// failed, so surface it as destructive.
export function statusVariant(
  status: InferenceStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'PROCESSED':
    case 'SAVED':
      return 'default'
    case 'REQUESTED':
      return 'destructive'
    default:
      return 'secondary'
  }
}

// Human label for the abnormal states. PROCESSED/SAVED are the quiet default
// (cards don't badge success); the proxy leaves failed runs in REQUESTED.
export function statusLabel(status: InferenceStatus): string {
  switch (status) {
    case 'REQUESTED':
      return 'failed'
    case 'PROCESSING':
      return 'running'
    case 'QUEUED':
      return 'queued'
    default:
      return status.toLowerCase()
  }
}

// A request is retryable when the viewer owns it and it failed — i.e. it's not
// a success (PROCESSED) and isn't currently running (PROCESSING). The proxy
// leaves failed runs in REQUESTED.
export function isRetryable(req: InferenceRequest): boolean {
  return !!req.is_owner && req.status !== 'PROCESSED' && req.status !== 'PROCESSING'
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return 'unknown'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return new Date(iso).toLocaleString()
}

export function formatAbsolute(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function totalTokens(req: InferenceRequest): number | null {
  const u = req.usage
  if (!u) return null
  if (typeof u.total_tokens === 'number') return u.total_tokens
  const sum = (u.prompt_tokens ?? 0) + (u.completion_tokens ?? 0)
  return sum > 0 ? sum : null
}

// Tailwind classes for the role label chip on a chat message.
export function roleClasses(role: string): string {
  switch (role) {
    case 'user':
      return 'bg-primary/10 text-primary border-primary/20'
    case 'assistant':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
    case 'system':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
    case 'tool':
      return 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}
