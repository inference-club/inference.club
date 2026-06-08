// A one-shot handoff for "Reproduce in playground": a request's stored
// parameters are stashed in sessionStorage, the user is sent to the matching
// playground page, and that page reads (and clears) the prefill on mount so it
// can populate its form. Kept tiny and type-tagged so a stale prefill for one
// modality never leaks into another page.

const KEY = 'playground-prefill'

export interface PlaygroundPrefill {
  type: string
  payload: Record<string, unknown>
}

// inference_type → playground route. Only the prompt-based, single-shot
// generative modalities are reproducible (file-input types like STT/MESH need
// the original upload, which the composer can't pre-fill).
export const REPRODUCE_ROUTES: Record<string, string> = {
  MUSIC: '/dashboard/playground/music',
  IMAGE: '/dashboard/playground/images',
  TTS: '/dashboard/playground/speech',
}

export function usePlaygroundPrefill() {
  const set = (type: string, payload: Record<string, unknown>) => {
    if (typeof sessionStorage === 'undefined') return
    sessionStorage.setItem(KEY, JSON.stringify({ type, payload }))
  }

  // Returns the payload if a prefill for `type` is pending, else null. Always
  // clears the stash so a back-navigation doesn't re-apply it.
  const take = (type: string): Record<string, unknown> | null => {
    if (typeof sessionStorage === 'undefined') return null
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    sessionStorage.removeItem(KEY)
    try {
      const parsed = JSON.parse(raw) as PlaygroundPrefill
      return parsed.type === type ? parsed.payload : null
    } catch {
      return null
    }
  }

  return { set, take }
}
