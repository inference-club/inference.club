export type InferenceType = 'LLM' | 'IMAGE' | 'VIDEO' | 'TTS'

export type InferenceStatus =
  | 'REQUESTED'
  | 'QUEUED'
  | 'PROCESSING'
  | 'PROCESSED'
  | 'SAVED'

export interface TokenUsage {
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
}

export interface ProviderMini {
  id: number
  name: string
}

export interface ChatMessage {
  role: string
  content: string
}

export interface InferenceRequest {
  id: string
  inference_type: InferenceType
  status: InferenceStatus
  model_name?: string
  provider?: ProviderMini | null
  latency_ms?: number | null
  ttft_ms?: number | null
  tokens_per_second?: number | null
  usage?: TokenUsage | null
  streamed?: boolean
  created_on: string
  modified_on: string

  // Owner attribution (present on both list and detail)
  owner?: string
  github_login?: string | null
  is_owner?: boolean

  // List (slim) serializer only
  prompt_preview?: string
  response_preview?: string
  message_count?: number
  has_reasoning?: boolean

  // Detail serializer only
  messages?: ChatMessage[]
  response_text?: string
  reasoning?: string
  payload?: Record<string, unknown>
  results?: Record<string, unknown>
}
