export type InferenceType = 'LLM' | 'STT' | 'IMAGE' | 'VIDEO' | 'TTS' | 'MESH' | 'MUSIC' | 'VOICE' | 'ENHANCE'

// Generation stats for an image-to-3D (MESH) request, mirrored from the
// upstream X-Trellis-Metadata header.
export interface MeshMeta {
  seed?: number
  resolution?: string
  vertices?: number
  faces?: number
  timing_sec?: Record<string, number>
}

// Generation stats for a text/image-to-video (VIDEO) request, derived from the
// resolved params LTX returns in its X-LTX-Params header.
export interface VideoMeta {
  seconds?: number
  width?: number
  height?: number
  fps?: number
  num_frames?: number
  seed?: number
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
  owner_handle?: string | null
  is_online?: boolean
}

// Where a request ran (detail view only), resolved from dispatch metadata.
export interface RequestHost {
  host_id?: string | null
  gpus?: string[]
}

export interface ChatMessage {
  role: string
  content: string
}

export interface InferenceRequest {
  id: string
  // Opaque public id used in URLs instead of the sequential PK.
  public_id?: string | null
  inference_type: InferenceType
  status: InferenceStatus
  model_name?: string
  provider?: ProviderMini | null
  host?: RequestHost | null
  latency_ms?: number | null
  ttft_ms?: number | null
  tokens_per_second?: number | null
  usage?: TokenUsage | null
  streamed?: boolean
  created_on: string
  modified_on: string

  // Audio modalities (STT, TTS, and MUSIC)
  audio_seconds?: number | null
  audio_url?: string | null // input audio (STT)
  output_audio_url?: string | null // generated audio (TTS / MUSIC)
  transcription?: TranscriptionExtras | null

  // Image generation
  image_count?: number | null
  image_urls?: string[]
  input_image_url?: string | null
  // Every source image for an edit (one for a classic edit, several when a
  // model fuses multiple reference images). `input_image_url` is the first.
  input_image_urls?: string[]

  // Image-to-3D (MESH): the generated GLB + its generation stats. The input
  // image is carried in `input_image_url` above (shared with image edits).
  model_url?: string | null
  mesh?: MeshMeta | null

  // Text/image-to-video (VIDEO): the generated MP4 + its generation stats. The
  // optional first-frame image is carried in `input_image_url` above.
  video_url?: string | null
  video?: VideoMeta | null

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
  // Staff curation for the home-page showcase (world-readable flag).
  is_featured?: boolean

  // Cover art (docs/prd/06-media-playback-experience.md): square artwork from
  // a linked IMAGE request, shown for MUSIC tracks in the player/playlists.
  cover_image_url?: string | null

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

// One entry in the home-page featured showcase: a PUBLIC request (list-card
// shape) plus the provider's GPU models and a guaranteed share token.
export interface FeaturedItem extends InferenceRequest {
  share_token: string
  gpus: string[]
  featured_at: string
}

// A user-named group of inference requests.
export interface Collection {
  id: number
  name: string
  slug: string
  description: string
  visibility: Visibility
  item_count: number
  // Per-modality counts + total music runtime, so list views can decide which
  // playback affordances (music playlist / video playlist) to offer.
  audio_count?: number
  video_count?: number
  total_audio_seconds?: number | null
  cover_image_url?: string | null
  owner?: string
  github_login?: string | null
  is_owner?: boolean
  created_on: string
  modified_on: string
  // Populated by the collection-detail endpoint.
  items?: InferenceRequest[]
}
