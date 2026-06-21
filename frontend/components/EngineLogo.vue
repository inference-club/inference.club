<script setup lang="ts">
// Brand mark for an inference engine — a rounded, brand-colored tile with a
// distinctive glyph. The single source of engine visual identity: reuse
// anywhere a service's engine needs a logo (machine cards, summaries, lists).
//
// These are original geometric marks (not the vendors' trademarked logos) so
// the set stays cohesive and self-contained — no runtime icon fetches. To swap
// in a true brand SVG later, replace the matching <template> glyph below.
import { ENGINE_BRAND, engineBrand } from '@/composables/useEngines'

const props = withDefaults(
  defineProps<{
    engine: string
    // px size of the square tile
    size?: number
    // hide the tile background (glyph only, inherits currentColor)
    bare?: boolean
  }>(),
  { size: 28, bare: false },
)

const brand = computed(() => engineBrand(props.engine))
const key = computed(() => (props.engine in ENGINE_BRAND ? props.engine : 'other'))
const stroke = computed(() => (props.bare ? 2 : 1.9))
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[7px]"
    :style="bare
      ? { width: `${size}px`, height: `${size}px`, color: brand.color }
      : { width: `${size}px`, height: `${size}px`, backgroundColor: brand.color, color: brand.fg }"
    :title="brand.label"
    :aria-label="brand.label"
  >
    <svg
      :width="size * 0.62"
      :height="size * 0.62"
      viewBox="0 0 24 24"
      fill="none"
      :stroke="bare ? 'currentColor' : brand.fg"
      :stroke-width="stroke"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <!-- vLLM: lightning — fast serving -->
      <template v-if="key === 'vllm'">
        <path d="M13 2 L4.5 13.5 H11 L10 22 L19.5 9 H13 Z" :fill="bare ? 'currentColor' : brand.fg" stroke="none" />
      </template>

      <!-- LM Studio: stacked desktop layers -->
      <template v-else-if="key === 'lmstudio'">
        <rect x="4" y="5.5" width="16" height="4" rx="1.4" :fill="bare ? 'currentColor' : brand.fg" stroke="none" />
        <rect x="4" y="11" width="16" height="4" rx="1.4" :fill="bare ? 'currentColor' : brand.fg" stroke="none" opacity="0.78" />
        <rect x="4" y="16.5" width="10" height="4" rx="1.4" :fill="bare ? 'currentColor' : brand.fg" stroke="none" opacity="0.56" />
      </template>

      <!-- Ollama: friendly llama silhouette -->
      <template v-else-if="key === 'ollama'">
        <g :fill="bare ? 'currentColor' : brand.fg" stroke="none">
          <path d="M7.6 3.2c.9 0 1.5.9 1.5 2.1 0 .5-.1 1-.3 1.4.7-.2 1.5-.3 2.2-.3s1.5.1 2.2.3c-.2-.4-.3-.9-.3-1.4 0-1.2.6-2.1 1.5-2.1s1.5 1 1.5 2.4c0 .8-.2 1.5-.6 2 1.1.9 1.8 2.1 1.8 3.6v.6c.6.5 1 1.2 1 2.1 0 .7-.3 1.3-.7 1.8.2.4.3.9.3 1.4 0 .7-.4 1.2-1 1.2-.4 0-.8-.3-1-.7-.6.3-1.2.4-1.9.4h-3.6c-.7 0-1.3-.1-1.9-.4-.2.4-.6.7-1 .7-.6 0-1-.5-1-1.2 0-.5.1-1 .3-1.4-.4-.5-.7-1.1-.7-1.8 0-.9.4-1.6 1-2.1v-.6c0-1.5.7-2.7 1.8-3.6-.4-.5-.6-1.2-.6-2 0-1.4.6-2.4 1.5-2.4Z" />
        </g>
      </template>

      <!-- SGLang: structured-generation braces -->
      <template v-else-if="key === 'sglang'">
        <path d="M9.5 3.5c-2 0-2.2 1.4-2.2 3.2 0 1.6-.2 2.6-1.8 2.6v1.4c1.6 0 1.8 1 1.8 2.6 0 1.8.2 3.2 2.2 3.2" :stroke="bare ? 'currentColor' : brand.fg" />
        <path d="M14.5 3.5c2 0 2.2 1.4 2.2 3.2 0 1.6.2 2.6 1.8 2.6v1.4c-1.6 0-1.8 1-1.8 2.6 0 1.8-.2 3.2-2.2 3.2" :stroke="bare ? 'currentColor' : brand.fg" transform="translate(0 3)" />
      </template>

      <!-- llama.cpp: terminal prompt -->
      <template v-else-if="key === 'llamacpp'">
        <rect x="3" y="4.5" width="18" height="15" rx="2.5" :stroke="bare ? 'currentColor' : brand.fg" />
        <path d="M7 10l2.5 2L7 14" :stroke="bare ? 'currentColor' : brand.fg" />
        <path d="M12.5 14.5H16" :stroke="bare ? 'currentColor' : brand.fg" />
      </template>

      <!-- TGI: hugging-face style smile -->
      <template v-else-if="key === 'tgi'">
        <circle cx="12" cy="12" r="8.5" :stroke="bare ? 'currentColor' : brand.fg" />
        <path d="M8.3 9.2h.01M15.7 9.2h.01" :stroke="bare ? 'currentColor' : brand.fg" stroke-width="2.4" />
        <path d="M8 14c1 1.4 2.4 2.1 4 2.1s3-.7 4-2.1" :stroke="bare ? 'currentColor' : brand.fg" />
      </template>

      <!-- other / unknown engine: generic chip -->
      <template v-else>
        <rect x="6.5" y="6.5" width="11" height="11" rx="2" :stroke="bare ? 'currentColor' : brand.fg" />
        <path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3" :stroke="bare ? 'currentColor' : brand.fg" />
      </template>
    </svg>
  </span>
</template>
