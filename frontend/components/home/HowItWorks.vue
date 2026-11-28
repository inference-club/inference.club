<script setup lang="ts">
// "How it works" as a scroll story. The 3D scene stays pinned while five
// short steps scroll past; whichever step is nearest the middle of the screen
// drives the scene. The scene (and three.js with it) is only loaded once the
// section is close to the viewport.
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { Home, Layers, Route, Lock, Bot } from 'lucide-vue-next'

const ClubScene = defineAsyncComponent(() => import('./ClubScene.vue'))

const props = defineProps<{ art?: string[] }>()
const { t, tm, rt } = useI18n()

const ICONS = [Home, Layers, Route, Lock, Bot]
const steps = computed(() =>
  ICONS.map((icon, i) => ({
    icon,
    title: t(`landing.how.steps.${i}.title`),
    body: t(`landing.how.steps.${i}.body`),
  })),
)

const list = (key: string) => (tm(key) as unknown[]).map((m) => rt(m as never))
// A stable object: the scene bakes label text into textures and rebuilds when
// this changes (language switch), so it must not be recreated per render.
const labels = computed(() => ({
  hub: 'inference.club',
  gallery: t('landing.how.scene.gallery'),
  membersOnly: t('landing.how.scene.membersOnly'),
  households: list('landing.how.scene.households') as [string, string, string, string],
  hardware: ['2× RTX 4090', 'DGX Spark', 'RTX 5090', 'RTX 4090'] as [string, string, string, string],
  requesters: list('landing.how.scene.requesters') as [string, string, string],
  modalities: {
    chat: t('landing.kinds.chat'),
    image: t('landing.kinds.image'),
    music: t('landing.kinds.music'),
    video: t('landing.kinds.video'),
    speech: t('landing.kinds.speech'),
    listen: t('landing.kinds.listen'),
  },
}))

const root = ref<HTMLElement | null>(null)
const stepEls = ref<HTMLElement[]>([])
const active = ref(0)
const near = ref(false)
let nearIo: IntersectionObserver | null = null
let ticking = false

// The active step is the one whose card is closest to 60% down the screen.
const measure = () => {
  ticking = false
  // Phones pin the scene to the top half, so cards are read in the lower half.
  const line = window.innerHeight * (window.innerWidth < 1024 ? 0.74 : 0.55)
  let best = 0
  let bestDist = Infinity
  stepEls.value.forEach((el, i) => {
    const r = el.getBoundingClientRect()
    const d = Math.abs((r.top + r.bottom) / 2 - line)
    if (d < bestDist) { bestDist = d; best = i }
  })
  active.value = best
}
const onScroll = () => {
  if (!ticking) { ticking = true; requestAnimationFrame(measure) }
}

onMounted(() => {
  nearIo = new IntersectionObserver(
    ([e]) => {
      if (e.isIntersecting) { near.value = true; nearIo?.disconnect() }
    },
    { rootMargin: '800px 0px' },
  )
  if (root.value) nearIo.observe(root.value)
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
  measure()
})
onBeforeUnmount(() => {
  nearIo?.disconnect()
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
})

const jump = (i: number) =>
  stepEls.value[i]?.scrollIntoView({ behavior: 'smooth', block: window.innerWidth < 1024 ? 'end' : 'center' })
</script>

<template>
  <section ref="root" class="relative border-y bg-muted/20" data-testid="how-it-works">
    <div class="mx-auto max-w-6xl px-4 pt-16 text-center sm:px-6 sm:pt-24 lg:px-8">
      <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ t('landing.how.eyebrow') }}</p>
      <h2 class="text-3xl font-bold tracking-tight sm:text-5xl">{{ t('landing.how.title') }}</h2>
      <p class="mx-auto mt-4 max-w-2xl text-muted-foreground">{{ t('landing.how.subtitle') }}</p>
    </div>

    <div class="relative mx-auto max-w-7xl lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-6 lg:px-8">
      <!-- The pinned scene. On phones it holds the top of the screen and the
           steps scroll beneath it; on desktop it holds the right-hand side. -->
      <div class="sticky top-14 z-20 h-[44svh] border-b bg-background lg:order-2 lg:top-16 lg:z-0 lg:h-[calc(100svh-5rem)] lg:border-0 lg:bg-transparent">
        <div
          class="pointer-events-none absolute inset-0 opacity-[0.08] dark:opacity-[0.14]"
          :style="{ backgroundImage: 'radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)', backgroundSize: '26px 26px' }"
        />
        <div class="pointer-events-none absolute inset-0 dark:bg-[radial-gradient(ellipse_at_center,rgba(99,102,241,0.16),transparent_65%)]" />
        <ClubScene v-if="near" :step="active" :labels="labels" :art="props.art" />
        <!-- Step dots -->
        <div class="absolute inset-x-0 bottom-2 flex justify-center gap-1.5 lg:bottom-6">
          <button
            v-for="(s, i) in steps"
            :key="i"
            type="button"
            class="h-1.5 rounded-full transition-all"
            :class="i === active ? 'w-6 bg-primary' : 'w-1.5 bg-foreground/25 hover:bg-foreground/50'"
            :aria-label="s.title"
            :aria-current="i === active ? 'step' : undefined"
            @click="jump(i)"
          />
        </div>
      </div>

      <ol class="relative z-10 px-4 pb-[8svh] pt-4 sm:px-6 lg:order-1 lg:px-0 lg:pb-[30svh] lg:pt-[20svh]">
        <li
          v-for="(s, i) in steps"
          :key="i"
          :ref="(el) => { if (el) stepEls[i] = el as HTMLElement }"
          class="flex min-h-[44svh] items-start py-3 lg:min-h-[70svh] lg:items-center lg:py-0"
          :data-testid="`how-step-${i}`"
        >
          <div
            class="w-full rounded-2xl border bg-background/90 p-5 shadow-sm backdrop-blur transition-all duration-300 sm:p-6"
            :class="i === active ? 'border-primary/40 opacity-100' : 'opacity-50 lg:opacity-40'"
          >
            <div class="mb-3 flex items-center gap-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <component :is="s.icon" class="size-4.5" />
              </span>
              <span class="font-mono text-xs text-muted-foreground">{{ i + 1 }} / {{ steps.length }}</span>
            </div>
            <h3 class="text-xl font-semibold tracking-tight sm:text-2xl">{{ s.title }}</h3>
            <p class="mt-2 leading-relaxed text-muted-foreground">{{ s.body }}</p>
          </div>
        </li>
      </ol>
    </div>
  </section>
</template>
