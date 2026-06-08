export type InferenceType = 'LLM' | 'STT' | 'IMAGE' | 'VIDEO' | 'TTS' | 'MESH'

// Generation stats for an image-to-3D (MESH) request, mirrored from the
// upstream X-Trellis-Metadata header.
export interface MeshMeta {
  seed?: number
  resolution?: string
  vertices?: number
  faces?: number
  timing_sec?: Record<string, number>
}

// Content visibility — see docs/prd/01-content-sharing.md.
export type Visibility = 'PUBLIC' | 'UNLISTED' | 'PRIVATE' | 'SECRET'

// One word in a verbose_json transcription, with its time interval.
export interface TranscriptWord {
  word: string
  start?: number
  end?: number
}

export interface TranscriptSegment {
  id?: number
  text: string
  start?: number
  end?: number
}

export interface TranscriptionExtras {
  words?: TranscriptWord[]
  segments?: TranscriptSegment[]
  language?: string
  duration?: number
}

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

  // Audio modalities (STT now; TTS later)
  audio_seconds?: number | null
  audio_url?: string | null // input audio (STT)
  output_audio_url?: string | null // generated audio (TTS)
  transcription?: TranscriptionExtras | null

  // Image generation
  image_count?: number | null
  image_urls?: string[]
  input_image_url?: string | null

  // Image-to-3D (MESH): the generated GLB + its generation stats. The input
  // image is carried in `input_image_url` above (shared with image edits).
  model_url?: string | null
  mesh?: MeshMeta | null

  // Owner attribution (present on both list and detail)
  owner?: string
  github_login?: string | null
  is_owner?: boolean

  // Sharing & curation (docs/prd/01-content-sharing.md)
  visibility?: Visibility
  share_token?: string | null // owner-only; null for non-owners
  star_count?: number
  is_starred?: boolean
  is_bookmarked?: boolean

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

// A user-named group of inference requests.
export interface Collection {
  id: number
  name: string
  slug: string
  description: string
  visibility: Visibility
  item_count: number
  cover_image_url?: string | null
  owner?: string
  github_login?: string | null
  is_owner?: boolean
  created_on: string
  modified_on: string
  // Populated by the collection-detail endpoint.
  items?: InferenceRequest[]
}
