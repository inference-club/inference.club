<script setup lang="ts">
// One narration: what is being read, how far along it is, the finished audio
// with speed control, and every piece with the means to fix it. The page
// refreshes itself while work is under way and rebuilds the joined file when
// the chosen takes change.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import {
  ArrowLeft, AudioLines, BookOpen, Check, CircleStop, ExternalLink, ListChecks, Loader2, Mic, RefreshCw,
  SlidersHorizontal, TriangleAlert,
} from 'lucide-vue-next'
import { useNarration, clock, type Narration } from '@/composables/useNarration'
import { formatRelative } from '@/utils/inference'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.narrate' })

const { t } = useI18n()
const route = useRoute()
const api = useNarration()
const lightbox = useImageLightbox()
const id = computed(() => String(route.params.id))

const item = ref<Narration | null>(null)
const failed = ref(false)
const playingSegment = ref<number | null>(null)
const playTime = ref(0)
// Seconds into the piece that is playing, for word-by-word follow-along.
const pieceTime = computed(() => {
  const o = n.value?.mix.offsets?.find((x) => x.segment_id === playingSegment.value)
  return o ? playTime.value - o.start : null
})
const player = ref<{ playSegment: (id: number) => void } | null>(null)
const showLog = ref(false)
const mixing = ref(false)

const n = computed(() => item.value?.narration)
const segments = computed(() => item.value?.segments ?? [])
const busyPieces = computed(() => segments.value.some((s) => ['queued', 'generating'].includes(s.status)))
const live = computed(() => !!n.value?.active || busyPieces.value)
const toReview = computed(() => (n.value?.counts.flagged ?? 0) + (n.value?.counts.error ?? 0))
const done = computed(() => (n.value ? n.value.counts.ready + n.value.counts.flagged + n.value.counts.error : 0))

const STEPS = ['reading', 'planning', 'voicing', 'mixing'] as const
const stepState = (step: (typeof STEPS)[number]) => {
  const stage = n.value?.stage ?? ''
  if (stage === 'done') return 'done'
  const at = STEPS.indexOf(stage as (typeof STEPS)[number])
  const mine = STEPS.indexOf(step)
  if (at < 0) return mine === 0 ? 'todo' : 'todo'
  return mine < at ? 'done' : mine === at ? 'now' : 'todo'
}
const MODEL_ORDER = ['voice', 'clean', 'check', 'judge', 'cover', 'read']
const models = computed(() => MODEL_ORDER.filter((k) => n.value?.models[k]).map((k) => ({ job: k, model: n.value!.models[k] })))
const elapsed = computed(() => {
  if (!n.value?.started) return ''
  const end = n.value.finished ? new Date(n.value.finished).getTime() : Date.now()
  return clock((end - new Date(n.value.started).getTime()) / 1000)
})

const load = async () => {
  try {
    item.value = await api.fetchOne(id.value)
    failed.value = false
  } catch {
    if (!item.value) failed.value = true
  }
}

// Refresh while anything is happening; when the pieces settle and the joined
// file is out of date, rebuild it without being asked.
let timer: ReturnType<typeof setTimeout> | null = null
const tick = async () => {
  await load()
  const cur = item.value
  if (cur && !live.value && !mixing.value && cur.narration.stage && !cur.narration.mix_current
    && segments.value.some((s) => s.selected_variant_id) && ['done', 'stopped', 'error'].includes(cur.narration.stage)) {
    await remix(true)
  }
  timer = setTimeout(tick, live.value ? 2000 : 15000)
}
onMounted(tick)
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })

const remix = async (quiet = false) => {
  if (!item.value || mixing.value) return
  mixing.value = true
  try {
    item.value = await api.mix(item.value.id)
    if (!quiet) toast.success(t('narrate.remixed'))
  } catch {
    if (!quiet) toast.error(t('narrate.remixFailed'))
  } finally {
    mixing.value = false
  }
}
const stop = async () => {
  if (!item.value) return
  await api.cancel(item.value.id).catch(() => {})
  toast.success(t('narrate.stopping'))
  load()
}
const resume = async () => {
  if (!item.value) return
  try {
    await api.resume(item.value.id)
    toast.success(t('narrate.resumed'))
    load()
  } catch {
    toast.error(t('narrate.piece.failed'))
  }
}

useHead(() => ({ title: item.value?.title }))
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 py-5 sm:px-6 sm:py-8">
    <NuxtLink to="/dashboard/narrate" class="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" /> {{ t('narrate.back') }}
    </NuxtLink>

    <div v-if="failed" class="py-16 text-center text-muted-foreground">{{ t('narrate.notFound') }}</div>
    <div v-else-if="!item" class="space-y-4">
      <div class="h-8 w-2/3 animate-pulse rounded bg-muted" />
      <div class="h-40 animate-pulse rounded-2xl bg-muted" />
    </div>

    <template v-else>
      <!-- What is being read -->
      <header class="mb-5 flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start">
        <button
          v-if="item.cover_image_url"
          type="button"
          class="w-full shrink-0 cursor-zoom-in sm:w-56"
          :aria-label="t('request.openImage')"
          @click="lightbox.open(item.cover_image_url)"
        >
          <img :src="item.cover_image_url" :alt="item.title" class="aspect-[7/4] w-full rounded-xl border object-cover" data-testid="narration-cover" />
        </button>
        <div v-else class="flex aspect-[7/4] w-full shrink-0 items-center justify-center rounded-xl border bg-muted sm:w-56">
          <Loader2 v-if="n?.models.cover && live" class="size-5 animate-spin text-muted-foreground" />
          <AudioLines v-else class="size-6 text-muted-foreground" />
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="text-xl font-bold leading-snug tracking-tight break-words sm:text-2xl" data-testid="narration-title">{{ item.title }}</h1>
          <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span v-if="item.source.author" class="font-medium text-foreground">{{ item.source.author }}</span>
            <span v-if="item.source.published">{{ new Date(item.source.published + 'T12:00:00').toLocaleDateString(undefined, { dateStyle: 'medium' }) }}</span>
            <a
              v-if="item.source.url"
              :href="item.source.url"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1 underline-offset-2 hover:underline"
            >{{ item.source.site || t('narrate.original') }} <ExternalLink class="size-3" /></a>
            <span v-if="item.source.words">{{ t('narrate.words', { n: item.source.words.toLocaleString() }) }}</span>
          </p>
          <p class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span v-if="item.voice_sample_name" class="inline-flex items-center gap-1"><Mic class="size-3" /> {{ t('narrate.inVoice', { name: item.voice_sample_name }) }}</span>
            <span>{{ formatRelative(item.created_on) }}</span>
            <NuxtLink :to="`/dashboard/studio/${item.id}`" class="inline-flex items-center gap-1 underline-offset-2 hover:underline">
              <SlidersHorizontal class="size-3" /> {{ t('narrate.openStudio') }}
            </NuxtLink>
          </p>
        </div>
      </header>

      <!-- Where it stands -->
      <section
        v-if="n && n.stage && (n.active || n.stage !== 'done')"
        class="mb-5 rounded-2xl border p-4"
        :class="n.stage === 'error' ? 'border-destructive/40 bg-destructive/5' : 'bg-card'"
        data-testid="narration-progress"
        aria-live="polite"
      >
        <div v-if="n.stage === 'error'" class="flex items-start gap-2 text-sm">
          <TriangleAlert class="mt-0.5 size-4 shrink-0 text-destructive" />
          <div class="min-w-0">
            <p class="font-medium">{{ t('narrate.stage.error') }}</p>
            <p class="text-muted-foreground break-words">{{ n.events[n.events.length - 1]?.message || n.error }}</p>
          </div>
        </div>
        <template v-else>
          <ol class="mb-3 grid grid-cols-4 gap-1.5 text-center text-[11px] sm:text-xs">
            <li v-for="step in STEPS" :key="step" :data-state="stepState(step)">
              <span
                class="mx-auto mb-1 flex size-7 items-center justify-center rounded-full border"
                :class="{
                  'border-emerald-500 bg-emerald-500 text-white': stepState(step) === 'done',
                  'border-primary text-primary': stepState(step) === 'now',
                  'text-muted-foreground': stepState(step) === 'todo',
                }"
              >
                <Check v-if="stepState(step) === 'done'" class="size-3.5" />
                <Loader2 v-else-if="stepState(step) === 'now' && n.active" class="size-3.5 animate-spin" />
                <component :is="{ reading: BookOpen, planning: ListChecks, voicing: Mic, mixing: AudioLines }[step]" v-else class="size-3.5" />
              </span>
              <span :class="stepState(step) === 'now' ? 'font-medium text-foreground' : 'text-muted-foreground'">{{ t(`narrate.stage.${step}`) }}</span>
            </li>
          </ol>
          <div class="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" :aria-valuenow="Math.round(n.fraction * 100)" aria-valuemin="0" aria-valuemax="100">
            <div class="h-full rounded-full bg-primary transition-[width] duration-700" :style="{ width: `${Math.max(2, n.fraction * 100)}%` }" />
          </div>
          <div class="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm">
            <p class="min-w-0" data-testid="narration-status">
              <template v-if="n.stage === 'voicing'">{{ t('narrate.voicingCount', { done, total: n.counts.total }) }}</template>
              <template v-else>{{ t(`narrate.stageLong.${n.stage}`) }}</template>
              <span v-if="elapsed" class="text-muted-foreground"> · {{ elapsed }}</span>
            </p>
            <Button v-if="n.active" variant="outline" size="sm" class="gap-1.5" @click="stop">
              <CircleStop class="size-3.5" /> {{ t('narrate.stop') }}
            </Button>
            <Button v-else-if="n.stage === 'stopped'" size="sm" class="gap-1.5" @click="resume">
              <RefreshCw class="size-3.5" /> {{ t('narrate.resume') }}
            </Button>
          </div>
        </template>

        <!-- Which model does what -->
        <ul v-if="models.length" class="mt-3 flex flex-wrap gap-1.5">
          <li v-for="m in models" :key="m.job" class="inline-flex max-w-full items-baseline gap-1.5 rounded-full border bg-background px-2.5 py-1 text-xs">
            <span class="shrink-0 text-muted-foreground">{{ t(`narrate.jobs.${m.job}`) }}</span>
            <span class="truncate font-medium">{{ m.model }}</span>
          </li>
        </ul>

        <!-- What has happened -->
        <button type="button" class="mt-3 text-xs text-muted-foreground underline-offset-2 hover:underline" @click="showLog = !showLog">
          {{ showLog ? t('narrate.hideLog') : n.events[n.events.length - 1]?.message }}
        </button>
        <ol v-if="showLog" class="mt-2 space-y-1 text-xs text-muted-foreground">
          <li v-for="(e, i) in n.events" :key="i" class="flex gap-2">
            <time class="shrink-0 font-mono tabular-nums">{{ new Date(e.at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</time>
            <span class="min-w-0 break-words">{{ e.message }}</span>
          </li>
        </ol>
      </section>

      <!-- Listen -->
      <section v-if="item.audio_url" class="sticky top-14 z-10 mb-5">
        <NarrationPlayer
          ref="player"
          :src="item.audio_url"
          :seconds="item.audio_seconds"
          :offsets="n?.mix.offsets"
          :download-name="`${item.title}.mp3`"
          @segment="playingSegment = $event"
          @time="playTime = $event"
        />
      </section>
      <p v-if="item.audio_url && n && !live" class="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span v-if="mixing" class="inline-flex items-center gap-1.5"><Loader2 class="size-3.5 animate-spin" /> {{ t('narrate.remixing') }}</span>
        <template v-else-if="toReview">
          <span class="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
            <TriangleAlert class="size-3.5" /> {{ t('narrate.toReview', { n: toReview }, toReview) }}
          </span>
          <button type="button" class="underline underline-offset-2" @click="resume">{{ t('narrate.retryThose') }}</button>
        </template>
        <span v-else class="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
          <Check class="size-3.5" /> {{ t('narrate.allGood') }}
        </span>
      </p>

      <!-- Every piece -->
      <section v-if="segments.length">
        <h2 class="mb-2 text-sm font-semibold">{{ t('narrate.pieces', { n: segments.length }, segments.length) }}</h2>
        <ol class="space-y-2">
          <NarratePiece
            v-for="(s, i) in segments"
            :key="s.id"
            :segment="s"
            :index="i"
            :kind="n?.kinds[String(s.id)]"
            :playing="playingSegment === s.id"
            :time="playingSegment === s.id ? pieceTime : null"
            :seekable="!!item.audio_url && !!n?.mix.offsets?.some((o) => o.segment_id === s.id)"
            @play="player?.playSegment(s.id)"
            @changed="load"
          />
        </ol>
      </section>
    </template>
  </div>
</template>
