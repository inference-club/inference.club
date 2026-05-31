import { Brain, Eye, Mic, Type, Video, Wrench } from 'lucide-vue-next'
import type { Component } from 'vue'

// Shared icon/label metadata for model capabilities, used by both the
// <ModelCapabilities> chips and the playground model dropdown so they stay in
// sync.
export const MODALITY_META: Record<string, { icon: Component; label: string }> = {
  text: { icon: Type, label: 'Text' },
  image: { icon: Eye, label: 'Image' },
  audio: { icon: Mic, label: 'Audio' },
  video: { icon: Video, label: 'Video' },
}

export const FEATURE_META: Record<string, { icon: Component; label: string }> = {
  reasoning: { icon: Brain, label: 'Reasoning' },
  tools: { icon: Wrench, label: 'Tools' },
}

// Compact context-length label, e.g. 128000 -> "125K ctx".
export const fmtCtx = (n?: number | null): string | null => {
  if (!n) return null
  return n >= 1000 ? `${Math.round(n / 1024)}K ctx` : `${n} ctx`
}
