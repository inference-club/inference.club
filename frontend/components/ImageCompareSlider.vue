<script setup lang="ts">
import { ref } from 'vue'
import { ChevronLeft, ChevronRight, Maximize2 } from 'lucide-vue-next'

// A draggable before/after split view. The "after" image is the base that
// sizes the box (object-contain); the "before" image is overlaid and clipped
// to the handle position, so dragging the handle wipes between the two.
const props = withDefaults(
  defineProps<{
    before: string
    after: string
    beforeLabel?: string
    afterLabel?: string
  }>(),
  { beforeLabel: 'Source', afterLabel: 'Result' },
)

const emit = defineEmits<{
  // Request the fullscreen lightbox — 'before' or 'after' picks the start image.
  (e: 'expand', which: 'before' | 'after'): void
}>()

const root = ref<HTMLElement | null>(null)
const pos = ref(50) // percent of the box revealed as "after" (handle x)
const dragging = ref(false)

const setFromClientX = (clientX: number) => {
  const el = root.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  pos.value = Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100))
}

const onPointerDown = (e: PointerEvent) => {
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  setFromClientX(e.clientX)
}
const onPointerMove = (e: PointerEvent) => {
  if (dragging.value) setFromClientX(e.clientX)
}
const onPointerUp = (e: PointerEvent) => {
  dragging.value = false
  ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
}
const onKey = (e: KeyboardEvent) => {
  if (e.key === 'ArrowLeft') pos.value = Math.max(0, pos.value - 4)
  else if (e.key === 'ArrowRight') pos.value = Math.min(100, pos.value + 4)
}
</script>

<template>
  <div
    ref="root"
    class="group/cmp relative touch-none select-none overflow-hidden rounded-lg border bg-muted/30"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <!-- Base: the result, sizes the box -->
    <img
      :src="props.after"
      class="block max-h-[75vh] w-full object-contain"
      draggable="false"
      loading="lazy"
      alt="Result"
    >

    <!-- Overlay: the source, clipped to the handle position -->
    <div
      class="pointer-events-none absolute inset-0 overflow-hidden"
      :style="{ clipPath: `inset(0 ${100 - pos}% 0 0)` }"
    >
      <img
        :src="props.before"
        class="absolute inset-0 h-full w-full object-contain"
        draggable="false"
        loading="lazy"
        alt="Source"
      >
    </div>

    <!-- Labels -->
    <span
      class="pointer-events-none absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-white"
    >
      {{ props.beforeLabel }}
    </span>
    <span
      class="pointer-events-none absolute right-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-white"
    >
      {{ props.afterLabel }}
    </span>

    <!-- Divider + handle -->
    <div
      class="pointer-events-none absolute inset-y-0 w-px bg-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.25)]"
      :style="{ left: `${pos}%` }"
    >
      <div
        role="slider"
        tabindex="0"
        aria-label="Compare source and result"
        :aria-valuenow="Math.round(pos)"
        aria-valuemin="0"
        aria-valuemax="100"
        class="pointer-events-auto absolute top-1/2 left-1/2 flex size-8 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full bg-white text-black shadow-lg outline-none ring-primary focus-visible:ring-2"
        @keydown="onKey"
      >
        <ChevronLeft class="size-3.5 -mr-1" />
        <ChevronRight class="size-3.5 -ml-1" />
      </div>
    </div>

    <!-- Expand to lightbox -->
    <button
      type="button"
      class="absolute bottom-2 right-2 flex size-7 items-center justify-center rounded-md bg-black/55 text-white opacity-0 transition-opacity hover:bg-black/75 group-hover/cmp:opacity-100"
      title="View fullscreen"
      @click.stop="emit('expand', 'after')"
    >
      <Maximize2 class="size-3.5" />
    </button>
  </div>
</template>
