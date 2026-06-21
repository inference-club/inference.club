// Visual identity for inference engines — brand color + label, keyed by the
// engine strings the agent + manifest validators accept (see ENGINE_LABELS in
// useManifest.ts). Rendered by <EngineLogo>; kept here so labels/colors live in
// one place and the logo component stays markup-only.

export interface EngineBrand {
  label: string
  // Tile background color (brand-ish, original marks — not trademarked logos).
  color: string
  // Glyph color that reads on `color`.
  fg: string
}

export const ENGINE_BRAND: Record<string, EngineBrand> = {
  vllm: { label: 'vLLM', color: '#4F46E5', fg: '#ffffff' },
  lmstudio: { label: 'LM Studio', color: '#7C5CFF', fg: '#ffffff' },
  ollama: { label: 'Ollama', color: '#0B1220', fg: '#ffffff' },
  sglang: { label: 'SGLang', color: '#0E9F6E', fg: '#ffffff' },
  llamacpp: { label: 'llama.cpp', color: '#C2562B', fg: '#ffffff' },
  tgi: { label: 'TGI', color: '#FFB000', fg: '#1f2937' },
  other: { label: 'Service', color: '#64748B', fg: '#ffffff' },
}

export const engineBrand = (engine?: string): EngineBrand =>
  ENGINE_BRAND[engine ?? 'other'] ?? ENGINE_BRAND.other

// Modality (service.type) → uppercase InferenceType used by <ModalityBadge>.
// Manifest types are lowercase (llm/stt/tts/image/mesh/music/video) plus a few
// backend-only ones; map the odd ones, uppercase the rest.
export const modalityType = (type?: string): string => {
  const t = (type || 'llm').toLowerCase()
  if (t === 'audio-enhance' || t === 'enhance') return 'ENHANCE'
  return t.toUpperCase()
}
