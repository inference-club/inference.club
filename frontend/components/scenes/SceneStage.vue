<script setup lang="ts" generic="O">
// The frame a scene plays in. Give it a scene loader and it does the rest:
// waits until the panel is near the viewport, loads three.js and the scene,
// rebuilds on a theme change, and tears down on unmount.
//
//   <SceneStage :load="() => import('@/lib/scenes/scenes/signals')" :options="{ art }" label="…">
//     <template #overlay> …HTML drawn over the canvas… </template>
//   </SceneStage>
//
// The default slot's sibling `#overlay` is for real text (labels, counters):
// text in HTML stays sharp, selectable and translatable.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { mountStage, type SceneFactory } from '@/lib/scenes/stage'
import { paletteFor } from '@/lib/scenes/theme'
import { useTheme } from '@/composables/useTheme'

const props = defineProps<{
  /** Lazy import of a module whose default export is the scene. */
  load: () => Promise<{ default: SceneFactory<O> }>
  /** Passed to the scene as `ctx.options`. Changing it rebuilds the scene. */
  options?: O
  /** What the picture shows, for people who cannot see it. */
  label: string
}>()
const emit = defineEmits<{ (e: 'state', name: string, value: unknown): void }>()

const { isDark } = useTheme()
const host = ref<HTMLDivElement | null>(null)
const ready = ref(false)
const failed = ref(false)
let teardown: (() => void) | null = null
let io: IntersectionObserver | null = null
let generation = 0

const start = async () => {
  const el = host.value
  if (!el) return
  const mine = ++generation
  teardown?.()
  teardown = null
  ready.value = false
  try {
    const mod = await props.load()
    if (mine !== generation || !host.value) return
    const stop = await mountStage(el, mod.default, {
      dark: isDark.value,
      options: props.options as O,
      onEmit: (name, value) => emit('state', name, value),
      onReady: () => (ready.value = true),
    })
    if (mine !== generation) stop()
    else teardown = stop
  } catch {
    // No WebGL, or the scene threw: the panel stays as a quiet backdrop.
    failed.value = true
  }
}

onMounted(() => {
  io = new IntersectionObserver(
    ([entry]) => {
      if (!entry.isIntersecting) return
      io?.disconnect()
      io = null
      start()
      // Palette and options are baked into the scene, so changes rebuild it.
      watch([isDark, () => props.options], start)
    },
    { rootMargin: '500px 0px' },
  )
  if (host.value) io.observe(host.value)
})
onBeforeUnmount(() => {
  generation++
  io?.disconnect()
  teardown?.()
})
</script>

<template>
  <div
    class="scene-stage relative isolate overflow-hidden"
    :style="{ '--scene-ground': paletteFor(isDark).ground, '--scene-ink': paletteFor(isDark).ink }"
    role="img"
    :aria-label="label"
    data-testid="scene-stage"
    :data-ready="ready || undefined"
  >
    <div
      ref="host"
      class="absolute inset-0 transition-opacity duration-1000"
      :class="ready ? 'opacity-100' : 'opacity-0'"
    />
    <div class="scene-glow pointer-events-none absolute inset-0" />
    <div class="pointer-events-none absolute inset-0"><slot name="overlay" /></div>
  </div>
</template>

<style scoped>
/* The panel is a piece of night sky (or a sheet of cream paper in the light
   theme). The canvas paints the ground colour itself; a faint warm glow is
   laid over it from the bottom edge. */
.scene-stage {
  color: var(--scene-ink);
  background: var(--scene-ground);
}
.scene-glow {
  background: radial-gradient(120% 70% at 50% 115%, color-mix(in oklab, #ffb44a 22%, transparent), transparent 62%);
}
</style>
