<script setup lang="ts">
// Bounding-box layout for models that advertise `layout-boxes` (FLUX 3 Image
// Klein): drag on the canvas to place an element, then say what goes there.
// Boxes are [y_min, x_min, y_max, x_max] in 0–1 with a top-left origin — the
// model's own convention — and guide placement and scale, not hard masks.
import { computed, ref } from 'vue'
import { X } from 'lucide-vue-next'

export interface LayoutBox { id: string; desc: string; bbox: [number, number, number, number] }

const props = defineProps<{ width: number; height: number }>()
const boxes = defineModel<LayoutBox[]>({ required: true })

const MAX_BOXES = 12
const COLORS = ['#f97316', '#0ea5e9', '#22c55e', '#a855f7', '#ef4444', '#eab308']
const color = (i: number) => COLORS[i % COLORS.length]

const canvas = ref<HTMLDivElement | null>(null)
const draft = ref<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
// Cap the drawing area's height so tall ratios don't take over the page.
const maxWidth = computed(() => `${Math.round(280 * (props.width / props.height))}px`)

const point = (e: PointerEvent) => {
  const r = canvas.value!.getBoundingClientRect()
  const clamp = (v: number) => Math.max(0, Math.min(1, v))
  return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) }
}
const onDown = (e: PointerEvent) => {
  if (boxes.value.length >= MAX_BOXES) return
  const p = point(e)
  draft.value = { x0: p.x, y0: p.y, x1: p.x, y1: p.y }
  canvas.value?.setPointerCapture(e.pointerId)
}
const onMove = (e: PointerEvent) => {
  if (!draft.value) return
  const p = point(e)
  draft.value = { ...draft.value, x1: p.x, y1: p.y }
}
const onUp = () => {
  const d = draft.value
  draft.value = null
  if (!d || Math.abs(d.x1 - d.x0) < 0.03 || Math.abs(d.y1 - d.y0) < 0.03) return
  const r = (v: number) => Math.round(v * 1000) / 1000
  const used = new Set(boxes.value.map((b) => b.id))
  let n = boxes.value.length + 1
  while (used.has(`obj_${n}`)) n++
  boxes.value = [...boxes.value, {
    id: `obj_${n}`,
    desc: '',
    bbox: [r(Math.min(d.y0, d.y1)), r(Math.min(d.x0, d.x1)), r(Math.max(d.y0, d.y1)), r(Math.max(d.x0, d.x1))],
  }]
}
const remove = (i: number) => { boxes.value = boxes.value.filter((_, j) => j !== i) }
const setDesc = (i: number, desc: string) => {
  boxes.value = boxes.value.map((b, j) => (j === i ? { ...b, desc } : b))
}
const style = (b: [number, number, number, number]) => ({
  top: `${b[0] * 100}%`, left: `${b[1] * 100}%`, height: `${(b[2] - b[0]) * 100}%`, width: `${(b[3] - b[1]) * 100}%`,
})
const draftBox = computed<[number, number, number, number] | null>(() => {
  const d = draft.value
  return d ? [Math.min(d.y0, d.y1), Math.min(d.x0, d.x1), Math.max(d.y0, d.y1), Math.max(d.x0, d.x1)] : null
})
</script>

<template>
  <div class="space-y-2">
    <div class="mx-auto w-full" :style="{ maxWidth }">
      <div
        ref="canvas"
        class="relative w-full cursor-crosshair touch-none select-none rounded-md border bg-muted/40"
        :style="{ aspectRatio: `${width} / ${height}` }"
        @pointerdown="onDown"
        @pointermove="onMove"
        @pointerup="onUp"
        @pointercancel="draft = null"
      >
        <div
          v-for="(b, i) in boxes"
          :key="b.id"
          class="pointer-events-none absolute rounded-sm border-2"
          :style="{ ...style(b.bbox), borderColor: color(i), backgroundColor: `${color(i)}22` }"
        >
          <span class="absolute left-0.5 top-0.5 rounded px-1 text-[10px] font-medium text-white" :style="{ backgroundColor: color(i) }">
            {{ i + 1 }}
          </span>
        </div>
        <div v-if="draftBox" class="pointer-events-none absolute rounded-sm border-2 border-dashed border-primary" :style="style(draftBox)" />
        <p v-if="!boxes.length && !draft" class="pointer-events-none absolute inset-0 flex items-center justify-center p-2 text-center text-[11px] text-muted-foreground">
          Drag to place an element
        </p>
      </div>
    </div>
    <div v-for="(b, i) in boxes" :key="b.id" class="flex items-center gap-1.5">
      <span class="size-2.5 shrink-0 rounded-full" :style="{ backgroundColor: color(i) }" />
      <Input
        :model-value="b.desc"
        :placeholder="`What goes in box ${i + 1}…`"
        class="h-7 text-xs"
        @update:model-value="(v: string | number) => setDesc(i, String(v))"
      />
      <Button variant="ghost" size="icon" class="size-7 shrink-0" :aria-label="`Remove box ${i + 1}`" @click="remove(i)">
        <X class="size-3.5" />
      </Button>
    </div>
  </div>
</template>
