export type InferenceType = 'LLM' | 'IMAGE' | 'VIDEO' | 'TTS'

export interface InferenceRequest {
  id: string
  inference_type: InferenceType
  payload: Record<string, unknown>
  status: 'REQUESTED' | 'QUEUED' | 'PROCESSING' | 'PROCESSED' | 'SAVED'
  created_on: string
  modified_on: string
  results?: Record<string, unknown>
}