<script setup lang="ts">
/**
 * Bespoke waveform player + trim editor for the Narration Studio.
 *
 * Draws the audio waveform on a canvas (decoded client-side via Web Audio) and
 * overlays the **removed** regions as draggable/resizable boxes — drag on empty
 * waveform to carve a new cut, drag a box to move it, grab an edge to resize, ×
 * to delete. "Preview cut" plays the clip while skipping the removed regions, so
 * you hear the trimmed result without re-encoding. Fully themed for light/dark.
 *
 * `modelValue` is the list of removed regions in SECONDS on this clip's timeline;
 * the parent turns it into a re-trim request.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Pause, Play, Scissors, X } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

interface Region { start: number; end: number }

const props = withDefaults(defineProps<{
  src: string | null
  modelValue: Region[]
  duration?: number
  height?: number
  readonly?: boolean
}>(), { duration: 0, height: 104, readonly: false })

const emit = defineEmits<{
  (e: 'update:modelValue', v: Region[]): void
  (e: 'time', t: number): void
}>()

const { isDark } = useTheme()

const wrap = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const peaks = ref<number[]>([])
const dur = ref(props.duration || 0)
const loading = ref(false)
const decodeFailed = ref(false)
const widthPx = ref(0)
const currentTime = ref(0)
const playing = ref(false)
// Default to previewing the result: playback skips removed regions so you hear
// the trimmed clip. Toggle off to audition the full take.
const skipCut = ref(true)

let audio: HTMLAudioElement | null = null
let raf = 0
let ro: ResizeObserver | null = null

const playheadPct = computed(() => (dur.value > 0 ? (currentTime.value / dur.value) * 100 : 0))

function regionStyle(r: Region) {
  if (dur.value <= 0) return { left: '0%', width: '0%' }
  const l = Math.max(0, Math.min(100, (r.start / dur.value) * 100))
  const w = Math.max(0, Math.min(100 - l, ((r.end - r.start) / dur.value) * 100))
  return { left: `${l}%`, width: `${w}%` }
}

const removedSeconds = computed(() =>
  props.modelValue.reduce((s, r) => s + Math.max(0, r.end - r.start), 0))

// ---- audio decode + peaks ---------------------------------------------------
async function loadAudio(src: string | null) {
  peaks.value = []
  decodeFailed.value = false
  if (!src || !import.meta.client) return
  loading.value = true
  try {
    const res = await fetch(src, { credentials: 'include' })
    const buf = await res.arrayBuffer()
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new AC()
    const decoded = await ctx.decodeAudioData(buf)
    dur.value = decoded.duration
    peaks.value = computePeaks(decoded, 1200)
    ctx.close()
  } catch {
    // Cross-origin media without CORS (or an unsupported codec): fall back to a
    // flat track — region editing still works off the <audio> duration.
    decodeFailed.value = true
  } finally {
    loading.value = false
    draw()
  }
}

function computePeaks(buffer: AudioBuffer, buckets: number): number[] {
  const ch = buffer.getChannelData(0)
  const block = Math.max(1, Math.floor(ch.length / buckets))
  const out: number[] = []
  let max = 0
  for (let i = 0; i < buckets; i++) {
    let peak = 0
    const start = i * block
    for (let j = 0; j < block; j++) {
      const v = Math.abs(ch[start + j] || 0)
      if (v > peak) peak = v
    }
    out.push(peak)
    if (peak > max) max = peak
  }
  return max > 0 ? out.map((v) => v / max) : out
}

// ---- canvas drawing ---------------------------------------------------------
function draw() {
  const c = canvas.value
  if (!c) return
  const w = widthPx.value || c.clientWidth
  const h = props.height
  if (w <= 0) return
  const dpr = window.devicePixelRatio || 1
  c.width = Math.floor(w * dpr)
  c.height = Math.floor(h * dpr)
  const ctx = c.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  const mid = h / 2
  const wave = isDark.value ? '#2dd4bf' : '#0d9488' // teal-400 / teal-600
  const n = peaks.value.length

  if (!n) {
    // placeholder centre line
    ctx.strokeStyle = isDark.value ? 'rgba(148,163,184,0.5)' : 'rgba(100,116,139,0.5)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, mid)
    ctx.lineTo(w, mid)
    ctx.stroke()
    return
  }

  ctx.strokeStyle = wave
  ctx.lineWidth = 1.4
  ctx.beginPath()
  const step = 2
  for (let x = 0; x < w; x += step) {
    const idx = Math.min(n - 1, Math.floor((x / w) * n))
    const p = peaks.value[idx] || 0
    const barH = Math.max(1, p * (h * 0.86))
    ctx.moveTo(x + 0.5, mid - barH / 2)
    ctx.lineTo(x + 0.5, mid + barH / 2)
  }
  ctx.stroke()
}

// ---- pointer interactions (create / move / resize) --------------------------
type DragMode = 'create' | 'move' | 'l' | 'r'
let drag: { mode: DragMode; index: number; downX: number; orig: Region; anchor: number; moved: boolean } | null = null
let pendingCreate: { t0: number; downX: number } | null = null

function rectX(clientX: number): number {
  const el = wrap.value
  if (!el) return 0
  const r = el.getBoundingClientRect()
  return Math.max(0, Math.min(r.width, clientX - r.left))
}
const xToTime = (x: number) => (widthPx.value > 0 && dur.value > 0 ? (x / widthPx.value) * dur.value : 0)

function onBgDown(e: PointerEvent) {
  wrap.value?.focus({ preventScroll: true })  // so k / Esc target this waveform
  if (props.readonly) return
  pendingCreate = { t0: xToTime(rectX(e.clientX)), downX: e.clientX }
  addWin()
}

function onRegionDown(e: PointerEvent, i: number, mode: DragMode) {
  wrap.value?.focus({ preventScroll: true })
  if (props.readonly) return
  const o = props.modelValue[i]
  // For an edge resize, anchor on the *opposite* edge so dragging past it flips
  // the side cleanly (drag left edge rightward past the right edge, etc.).
  const anchor = mode === 'l' ? o.end : mode === 'r' ? o.start : o.start
  drag = { mode, index: i, downX: e.clientX, orig: { ...o }, anchor, moved: false }
  addWin()
}

function onWinMove(e: PointerEvent) {
  if (pendingCreate) {
    if (Math.abs(e.clientX - pendingCreate.downX) < 4) return
    // promote to a real region; anchor at the press point so dragging either
    // direction (left→right OR right→left) carves the region from there.
    const t0 = pendingCreate.t0
    drag = { mode: 'create', index: props.modelValue.length, downX: pendingCreate.downX, orig: { start: t0, end: t0 }, anchor: t0, moved: true }
    pendingCreate = null
    emit('update:modelValue', clampAll([...props.modelValue, { start: t0, end: t0 }]))
    return
  }
  if (!drag) return
  drag.moved = true
  const t = xToTime(rectX(e.clientX))
  const list = props.modelValue.map((r) => ({ ...r }))
  const r = list[drag.index]
  if (!r) return
  const o = drag.orig
  if (drag.mode === 'move') {
    const dt = t - xToTime(rectX(drag.downX))
    const len = o.end - o.start
    const s = Math.max(0, Math.min(dur.value - len, o.start + dt))
    r.start = s; r.end = s + len
  } else {
    // create / resize: span between the fixed anchor and the pointer — works in
    // both directions and flips sides if you cross over.
    r.start = Math.max(0, Math.min(drag.anchor, t))
    r.end = Math.min(dur.value, Math.max(drag.anchor, t))
  }
  emit('update:modelValue', list)
}

function onWinUp(e: PointerEvent) {
  if (pendingCreate) {
    // a click with no drag → seek
    if (Math.abs(e.clientX - pendingCreate.downX) < 4) seek(pendingCreate.t0)
    pendingCreate = null
  }
  if (drag) {
    // drop slivers (an accidental tiny drag)
    const list = props.modelValue.filter((r) => r.end - r.start > 0.03)
    if (list.length !== props.modelValue.length) emit('update:modelValue', list)
    drag = null
  }
  removeWin()
}

function cancelDrag() {
  if (drag) {
    // Drop a region being created; restore one being moved/resized.
    const list = props.modelValue.map((r) => ({ ...r }))
    if (drag.mode === 'create') list.splice(drag.index, 1)
    else if (list[drag.index]) list[drag.index] = { ...drag.orig }
    emit('update:modelValue', list)
  }
  drag = null
  pendingCreate = null
  removeWin()
}

// Keyboard shortcuts when the waveform is focused (click it to focus):
//   k / Space — play / pause   ·   Esc — cancel a drag, else drop the last cut
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'k' || e.key === 'K' || e.key === ' ') {
    e.preventDefault()
    togglePlay()
    return
  }
  if (e.key === 'Escape') {
    e.preventDefault()
    if (drag || pendingCreate) { cancelDrag(); return }
    if (!props.readonly && props.modelValue.length) {
      emit('update:modelValue', props.modelValue.slice(0, -1))  // remove the just-made cut
    }
  }
}

function addWin() {
  window.addEventListener('pointermove', onWinMove)
  window.addEventListener('pointerup', onWinUp)
}
function removeWin() {
  window.removeEventListener('pointermove', onWinMove)
  window.removeEventListener('pointerup', onWinUp)
}

function clampAll(list: Region[]): Region[] {
  return list.map((r) => ({
    start: Math.max(0, Math.min(dur.value, Math.min(r.start, r.end))),
    end: Math.max(0, Math.min(dur.value, Math.max(r.start, r.end))),
  }))
}

function removeRegion(i: number) {
  emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i))
}

// Add a cut at a given time (used by the parent's "Add cut" button), ~0.4s wide,
// clamped into the clip; returns nothing — emits the updated list.
function addRegionAt(t: number, width = 0.4) {
  if (dur.value <= 0) return
  const start = Math.max(0, Math.min(dur.value - 0.05, t))
  const end = Math.min(dur.value, start + width)
  if (end - start < 0.03) return
  emit('update:modelValue', [...props.modelValue, { start, end }])
}

// ---- playback ---------------------------------------------------------------
function ensureAudio() {
  if (audio || !import.meta.client) return
  audio = new Audio()
  audio.preload = 'metadata'
  audio.addEventListener('loadedmetadata', () => { if (!dur.value && audio) dur.value = audio.duration })
  audio.addEventListener('ended', () => { playing.value = false; cancelAnimationFrame(raf) })
}

function tick() {
  if (!audio) return
  currentTime.value = audio.currentTime
  emit('time', audio.currentTime)
  if (skipCut.value) {
    const r = props.modelValue.find((rr) => audio!.currentTime >= rr.start && audio!.currentTime < rr.end - 0.01)
    if (r) audio.currentTime = r.end
  }
  if (playing.value) raf = requestAnimationFrame(tick)
}

function togglePlay() {
  ensureAudio()
  if (!audio || !props.src) return
  if (audio.src !== props.src) audio.src = props.src
  if (playing.value) {
    audio.pause(); playing.value = false; cancelAnimationFrame(raf)
  } else {
    // if paused inside a cut while previewing, jump out first
    if (skipCut.value) {
      const r = props.modelValue.find((rr) => audio!.currentTime >= rr.start && audio!.currentTime < rr.end - 0.01)
      if (r) audio.currentTime = r.end
    }
    audio.play().then(() => { playing.value = true; raf = requestAnimationFrame(tick) }).catch(() => {})
  }
}

function seek(t: number) {
  ensureAudio()
  if (!audio) return
  if (audio.src !== props.src && props.src) audio.src = props.src
  audio.currentTime = Math.max(0, Math.min(dur.value, t))
  currentTime.value = audio.currentTime
  emit('time', audio.currentTime)
}

const fmt = (s: number) => {
  if (!isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// ---- lifecycle --------------------------------------------------------------
onMounted(() => {
  ensureAudio()
  if (wrap.value) {
    widthPx.value = wrap.value.clientWidth
    ro = new ResizeObserver(() => { widthPx.value = wrap.value?.clientWidth || 0 })
    ro.observe(wrap.value)
  }
  loadAudio(props.src)
})

onBeforeUnmount(() => {
  removeWin()
  cancelAnimationFrame(raf)
  ro?.disconnect()
  if (audio) { audio.pause(); audio.src = '' }
})

watch(() => props.src, (s) => {
  playing.value = false
  currentTime.value = 0
  cancelAnimationFrame(raf)
  if (audio) { audio.pause(); audio.removeAttribute('src') }
  loadAudio(s)
})
watch([peaks, widthPx, isDark], draw)
watch(() => props.duration, (d) => { if (d && !dur.value) dur.value = d })

defineExpose({ seek, togglePlay, addRegionAt })
</script>

<template>
  <div class="space-y-2">
    <!-- waveform + regions -->
    <div
      ref="wrap"
      tabindex="0"
      class="relative w-full touch-none select-none overflow-hidden rounded-lg border bg-muted/40 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
      :style="{ height: `${height}px` }"
      :class="readonly ? '' : 'cursor-text'"
      @pointerdown="onBgDown"
      @keydown="onKeydown"
    >
      <canvas ref="canvas" class="absolute inset-0 block h-full w-full" />

      <!-- decode hint -->
      <div v-if="loading" class="absolute inset-0 grid place-items-center text-xs text-muted-foreground">
        decoding…
      </div>

      <!-- removed regions -->
      <div
        v-for="(r, i) in modelValue" :key="i"
        class="group absolute top-0 bottom-0"
        :style="regionStyle(r)"
      >
        <div
          class="absolute inset-0 border-x-2 border-rose-500/70 bg-rose-500/25"
          :class="readonly ? '' : 'cursor-grab active:cursor-grabbing'"
          :title="readonly ? '' : 'Drag to move · drag an edge to resize · double-click to delete'"
          @pointerdown.stop="onRegionDown($event, i, 'move')"
          @dblclick.stop="!readonly && removeRegion(i)"
        />
        <template v-if="!readonly">
          <div class="absolute inset-y-0 -left-0.5 w-2.5 cursor-ew-resize bg-rose-500/0 hover:bg-rose-500/50"
               @pointerdown.stop="onRegionDown($event, i, 'l')" />
          <div class="absolute inset-y-0 -right-0.5 w-2.5 cursor-ew-resize bg-rose-500/0 hover:bg-rose-500/50"
               @pointerdown.stop="onRegionDown($event, i, 'r')" />
          <button
            type="button" title="Remove this cut"
            class="absolute right-0 top-0 hidden size-5 place-items-center rounded-bl-md bg-rose-500 text-white hover:bg-rose-600 group-hover:grid"
            @pointerdown.stop @click.stop="removeRegion(i)"
          >
            <X class="size-3.5" />
          </button>
        </template>
      </div>

      <!-- playhead -->
      <div class="pointer-events-none absolute inset-y-0 w-px bg-sky-500" :style="{ left: `${playheadPct}%` }" />
    </div>

    <!-- transport -->
    <div class="flex items-center gap-2 text-xs">
      <button
        type="button"
        class="flex size-7 items-center justify-center rounded-md bg-fuchsia-500 text-white hover:bg-fuchsia-600 disabled:opacity-50"
        :disabled="!src" @click="togglePlay"
      >
        <component :is="playing ? Pause : Play" class="size-3.5" />
      </button>
      <span class="tabular-nums text-muted-foreground">{{ fmt(currentTime) }} / {{ fmt(dur) }}</span>
      <span class="hidden text-[10px] text-muted-foreground sm:inline" title="Keyboard: k or space to play/pause, Esc to undo the last cut">
        <kbd class="rounded border px-1">k</kbd> play · <kbd class="rounded border px-1">esc</kbd> undo cut
      </span>

      <button
        v-if="!readonly" type="button"
        class="ml-auto flex items-center gap-1 rounded-md border px-2 py-1 font-medium hover:bg-muted"
        :class="skipCut ? 'border-fuchsia-400 text-fuchsia-600 dark:text-fuchsia-400' : 'text-muted-foreground'"
        title="Play while skipping the removed regions" @click="skipCut = !skipCut"
      >
        <Scissors class="size-3" /> Preview cut
      </button>
      <span v-if="!readonly && modelValue.length" class="text-rose-500" :class="readonly ? '' : 'ml-1'">
        −{{ removedSeconds.toFixed(1) }}s
      </span>
      <span v-if="decodeFailed" class="ml-1 text-amber-600 dark:text-amber-400" title="Waveform unavailable (CORS); editing still works">
        no waveform
      </span>
    </div>
  </div>
</template>
