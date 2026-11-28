<script setup lang="ts">
// A model writing one sentence, with its odds showing. For every word it
// produced, the API also returns how likely that word was and what else it
// weighed; this plays them back one word at a time. The data is a real answer
// saved by scripts/showcase/generate.py (the "probabilities" item), not a mock.
//
// It plays by itself while on screen. Tapping a word stops the playback and
// shows that word's alternatives.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RotateCcw } from 'lucide-vue-next'
import showcase from '~/public/showcase/index.json'
import { paletteFor } from '@/lib/scenes/theme'
import { useTheme } from '@/composables/useTheme'
import { prettyGpuModel } from '@/composables/useMachineForm'

interface Tok { t: string; p: number; alts: Array<{ t: string; p: number }> }
interface Piece { id: string; kind: string; model: string; prompt?: string; gpu?: string | null; tokens?: Tok[] }

const { t } = useI18n()
const { isDark } = useTheme()
const palette = computed(() => paletteFor(isDark.value))

const piece = (showcase.items as Piece[]).find((p) => p.kind === 'logprobs')
const tokens = piece?.tokens ?? []

const shown = ref(tokens.length) // how many words are on the page (all, until it starts playing)
const focus = ref(Math.max(0, tokens.length - 1)) // whose alternatives are showing
const playing = ref(false)
const root = ref<HTMLElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let io: IntersectionObserver | null = null

const current = computed(() => tokens[focus.value])
const pct = (p: number) => (p >= 0.995 ? '100%' : p < 0.005 ? '<1%' : `${Math.round(p * 100)}%`)
// A sure word is plain ink; a toss-up is warm.
const tone = (p: number) => (p > 0.85 ? palette.value.ink : p > 0.45 ? palette.value.amber : palette.value.coral)
// Leading spaces are part of a token; show them as a real gap in the sentence
// and as a visible mark in the list of alternatives.
const visible = (s: string) => s.replace(/^ /, '␣').replace(/\n/g, '↵')

const stop = () => {
  playing.value = false
  if (timer) clearTimeout(timer)
  timer = null
}
const step = () => {
  if (!playing.value) return
  if (shown.value >= tokens.length) {
    // Rest on the finished sentence, then start over.
    timer = setTimeout(() => { shown.value = 0; step() }, 3200)
    return
  }
  shown.value += 1
  focus.value = shown.value - 1
  // Linger on the words where the model was unsure: they are the interesting ones.
  timer = setTimeout(step, tokens[focus.value].p < 0.6 ? 1500 : 650)
}
const play = () => {
  stop()
  playing.value = true
  shown.value = 0
  step()
}
const inspect = (i: number) => {
  stop()
  shown.value = tokens.length
  focus.value = i
}

onMounted(() => {
  if (!tokens.length || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  io = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && !playing.value && !timer) play()
    else if (!entry.isIntersecting) stop()
  }, { threshold: 0.4 })
  if (root.value) io.observe(root.value)
})
onBeforeUnmount(() => { stop(); io?.disconnect() })
</script>

<template>
  <div
    v-if="tokens.length"
    ref="root"
    class="token-odds rounded-3xl border p-5 sm:p-8"
    :style="{ '--ground': palette.ground, '--ink': palette.ink, '--dim': palette.dim, '--rule': palette.line, '--amber': palette.amber }"
    data-testid="token-probabilities"
  >
    <p class="text-sm" :style="{ color: palette.dim }">
      <span class="font-mono text-xs uppercase tracking-wider">{{ t('landing.scenes.thinking.asked') }}</span>
      {{ piece?.prompt }}
    </p>

    <!-- The sentence, one word at a time. -->
    <p class="mt-4 min-h-[9rem] text-2xl font-medium leading-snug sm:min-h-[7.5rem] sm:text-4xl" aria-live="off">
      <button
        v-for="(tok, i) in tokens.slice(0, shown)"
        :key="i"
        type="button"
        class="token rounded-sm transition-colors"
        :class="i === focus ? 'is-focus' : ''"
        :style="{ color: tone(tok.p), marginLeft: tok.t.startsWith(' ') && i ? '0.28em' : '0' }"
        :aria-label="`${tok.t.trim()} ${pct(tok.p)}`"
        @click="inspect(i)"
      >{{ tok.t.trim() }}</button><span v-if="playing && shown < tokens.length" class="caret" />
    </p>

    <!-- What else it weighed for the word in focus. -->
    <div class="mt-4 border-t pt-4" :style="{ borderColor: palette.line }">
      <p class="mb-2 font-mono text-xs uppercase tracking-wider" :style="{ color: palette.dim }">
        {{ t('landing.scenes.thinking.considered') }}
      </p>
      <!-- Five rows are always reserved, so the page below never jumps. -->
      <ul class="min-h-[7.75rem] space-y-1.5">
        <li
          v-for="(alt, k) in current?.alts ?? []"
          :key="`${focus}-${k}`"
          class="flex min-w-0 items-center gap-3 text-sm"
        >
          <span
            class="w-28 shrink-0 truncate font-mono sm:w-36"
            :style="{ color: alt.t === current?.t ? palette.ink : palette.dim, fontWeight: alt.t === current?.t ? 700 : 400 }"
          >{{ visible(alt.t) }}</span>
          <span class="h-2 min-w-0 flex-1 overflow-hidden rounded-full" :style="{ background: palette.line }">
            <span
              class="bar block h-full rounded-full"
              :style="{ width: `${Math.max(1, alt.p * 100)}%`, background: alt.t === current?.t ? palette.amber : palette.dim }"
            />
          </span>
          <span class="w-11 shrink-0 text-right font-mono tabular-nums" :style="{ color: palette.dim }">{{ pct(alt.p) }}</span>
        </li>
      </ul>
    </div>

    <div class="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs" :style="{ color: palette.dim }">
      <span class="min-w-0">
        {{ piece?.model }}<template v-if="piece?.gpu"> · {{ prettyGpuModel(piece.gpu) }}</template>
        · {{ t('landing.scenes.thinking.hint') }}
      </span>
      <button
        type="button"
        class="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 transition-colors hover:opacity-80"
        :style="{ borderColor: palette.line, color: palette.ink }"
        @click="play"
      >
        <RotateCcw class="size-3" /> {{ t('landing.scenes.thinking.replay') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.token-odds {
  color: var(--ink);
  border-color: var(--rule);
  background:
    radial-gradient(120% 80% at 50% 120%, color-mix(in oklab, #ffb44a 14%, transparent), transparent 60%),
    var(--ground);
}
.token {
  cursor: pointer;
  text-decoration: underline transparent 2px;
  text-underline-offset: 0.22em;
}
.token:hover,
.token.is-focus {
  text-decoration-color: var(--amber);
}
.caret {
  display: inline-block;
  width: 0.5em;
  height: 0.9em;
  margin-left: 0.15em;
  vertical-align: -0.08em;
  background: var(--amber);
  animation: blink 0.9s steps(2) infinite;
}
.bar {
  animation: grow 0.45s ease-out;
  transform-origin: left;
}
@keyframes blink { 50% { opacity: 0; } }
@keyframes grow { from { transform: scaleX(0); } }
@media (prefers-reduced-motion: reduce) {
  .caret, .bar { animation: none; }
}
</style>
