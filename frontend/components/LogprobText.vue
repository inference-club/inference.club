<script setup lang="ts">
// Renders an assistant reply as a sequence of confidence-coloured token spans.
// Each token's background fades toward transparent the more certain the model
// was; uncertain tokens glow amber→red. Hovering a token reveals its exact
// probability, raw logprob, and the alternatives the model weighed.
import { ref } from 'vue'
import type { TokenLogprob } from '@/composables/usePlayground'

defineProps<{ tokens: TokenLogprob[] }>()

const active = ref<number | null>(null)
// `below` flips the tooltip under the token when there isn't room above it
// (e.g. the first line of a reply sitting near the top of the viewport).
const tip = ref({ x: 0, y: 0, below: false })

const prob = (lp: number) => Math.exp(lp)
const pct = (lp: number) => {
  const p = prob(lp) * 100
  if (p >= 10) return p.toFixed(1) + '%'
  if (p >= 1) return p.toFixed(2) + '%'
  return p.toPrecision(2) + '%'
}

// Confident tokens (p→1) fade to near-transparent green; uncertain ones (p→0)
// glow stronger red. Low alpha keeps the underlying text readable in both
// themes, so the highlight stays out of the way until you look for it.
const bg = (lp: number) => {
  const p = prob(lp)
  const hue = p * 120 // 0 = red, 120 = green
  const alpha = 0.08 + (1 - p) * 0.4
  return `hsla(${hue}, 80%, 50%, ${alpha.toFixed(3)})`
}

const show = (i: number, e: MouseEvent) => {
  active.value = i
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const below = r.top < 170 // not enough headroom above — drop the tooltip down
  tip.value = { x: r.left + r.width / 2, y: below ? r.bottom : r.top, below }
}
const hide = () => {
  active.value = null
}

// Spell out whitespace tokens so the tooltip can name them.
const visible = (t: string) =>
  t.replace(/\n/g, '⏎').replace(/\t/g, '⇥').replace(/ /g, '·') || '∅'
</script>

<template>
  <div>
    <div class="text-sm leading-7 whitespace-pre-wrap font-sans">
      <span
        v-for="(tk, i) in tokens"
        :key="i"
        class="rounded-[3px] cursor-help transition-shadow"
        :class="active === i ? 'ring-1 ring-foreground/40' : ''"
        :style="{ backgroundColor: bg(tk.logprob) }"
        @mouseenter="show(i, $event)"
        @mouseleave="hide"
      >{{ tk.token }}</span>
    </div>

    <!-- Legend: tells you what the colours mean without crowding the text. -->
    <div class="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground select-none">
      <span>less likely</span>
      <span
        class="h-2 w-24 rounded"
        style="background: linear-gradient(to right, hsla(0,80%,50%,.45), hsla(60,80%,50%,.3), hsla(120,80%,50%,.18))"
      />
      <span>more likely</span>
      <span class="ml-1">· hover a token</span>
    </div>

    <Teleport to="body">
      <div
        v-if="active !== null && tokens[active]"
        class="fixed z-50 -translate-x-1/2 pointer-events-none"
        :class="tip.below ? '' : '-translate-y-full'"
        :style="{ left: tip.x + 'px', top: (tip.below ? tip.y + 8 : tip.y - 8) + 'px' }"
      >
        <div class="rounded-lg border bg-popover text-popover-foreground shadow-md px-3 py-2 text-xs w-56">
          <div class="flex items-center justify-between gap-2 mb-1.5">
            <code class="font-mono bg-muted px-1 py-0.5 rounded text-[11px] break-all">{{
              visible(tokens[active].token)
            }}</code>
            <span class="tabular-nums font-semibold shrink-0">{{ pct(tokens[active].logprob) }}</span>
          </div>
          <div class="text-muted-foreground tabular-nums mb-2">
            logprob {{ tokens[active].logprob.toFixed(3) }}
          </div>
          <template v-if="tokens[active].top_logprobs?.length">
            <div class="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
              Top alternatives
            </div>
            <div class="space-y-1">
              <div
                v-for="(alt, j) in tokens[active].top_logprobs"
                :key="j"
                class="flex items-center gap-1.5"
              >
                <code class="font-mono text-[11px] w-16 truncate shrink-0">{{ visible(alt.token) }}</code>
                <div class="flex-1 h-1.5 rounded bg-muted overflow-hidden">
                  <div class="h-full bg-primary/70" :style="{ width: prob(alt.logprob) * 100 + '%' }" />
                </div>
                <span class="tabular-nums text-[10px] text-muted-foreground w-10 text-right shrink-0">{{
                  pct(alt.logprob)
                }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </Teleport>
  </div>
</template>
