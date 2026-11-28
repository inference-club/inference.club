<script setup lang="ts">
// One inference request, laid out to be read: what was made, who made it and
// on what hardware, what they asked for, and (folded away) everything else.
// Used by the member detail page and the public share page, so the two never
// drift apart.
import { computed, ref } from 'vue'
import {
  Play, Pause, Download, Loader2, Copy, Check, ChevronDown, Brain, Server, Cpu, Box, Timer,
  Zap, Gauge, Hash, Ruler, Clock, Shapes, FileAudio, FileImage,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import type { InferenceRequest } from '@/types'
import { usePlayerStore } from '@/stores/player'
import { trackFromRequest, formatTrackTime } from '@/utils/player'
import {
  statusLabel, formatAbsolute, formatRelative, nodeUrl, roleClasses,
} from '@/utils/inference'
import {
  requestFacts, requestPrompt, requestSettings, requestSourceName, requestTitle,
} from '@/utils/requestView'

const props = defineProps<{ request: InferenceRequest }>()

const { t } = useI18n()
const req = computed(() => props.request)
const type = computed(() => req.value.inference_type)
const payload = computed(() => (req.value.payload ?? {}) as Record<string, unknown>)
const text = (k: string) => {
  const v = payload.value[k]
  return typeof v === 'string' && v !== 'None' ? v.trim() : ''
}

const title = computed(() => requestTitle(req.value, t(`request.kind.${type.value}`)))
const prompt = computed(() => requestPrompt(req.value))
const sourceName = computed(() => requestSourceName(req.value))
const lyrics = computed(() => {
  const l = text('lyrics')
  return l && l.toLowerCase() !== '[instrumental]' ? l : ''
})
const negative = computed(() => text('negative_prompt'))
const facts = computed(() => requestFacts(req.value, nodeUrl(req.value)))
const settings = computed(() => requestSettings(req.value))
const owner = computed(() => req.value.github_login || req.value.owner || '')
const failed = computed(() => req.value.status === 'REQUESTED')
const running = computed(() => ['PROCESSING', 'QUEUED'].includes(req.value.status))

const FACT_ICONS: Record<string, unknown> = {
  machine: Server, gpu: Cpu, model: Box, took: Timer, firstToken: Zap, speed: Gauge,
  tokens: Hash, length: Clock, size: Ruler, mesh: Shapes,
}

// Pictures the person supplied (edit sources, a video's first frame, the image
// a 3D model was built from).
const inputImages = computed(() =>
  req.value.input_image_urls?.length
    ? req.value.input_image_urls
    : req.value.input_image_url
      ? [req.value.input_image_url]
      : [],
)
const lightbox = useImageLightbox()

// Songs play through the global player so they survive navigation.
const player = usePlayerStore()
const track = computed(() => trackFromRequest(req.value))
const isCurrent = computed(() => !!track.value && player.current?.id === track.value.id)
const songPlaying = computed(() => isCurrent.value && player.playing)
const toggleSong = () => {
  if (!track.value) return
  if (isCurrent.value) player.toggle()
  else player.playTrack(track.value)
}
const songPct = computed(() =>
  isCurrent.value && player.duration > 0 ? (player.currentTime / player.duration) * 100 : 0,
)

const { downloading, download } = useFileDownload()

const copied = ref(false)
const copyPrompt = async () => {
  try {
    await navigator.clipboard.writeText(prompt.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    toast.error(t('request.copyFailed'))
  }
}

// Chat: everything before the answer is the conversation. A long system
// prompt is context, not content, so it starts folded.
const messages = computed(() => req.value.messages ?? [])
const finishReason = computed(() => {
  const r = req.value.results as { choices?: { finish_reason?: string }[] } | null | undefined
  return r?.choices?.[0]?.finish_reason ? String(r.choices[0].finish_reason) : ''
})
const pretty = (v: unknown) => JSON.stringify(v ?? {}, null, 2)
// A structured answer reads better laid out than as one run-on line.
const answerJson = computed(() => {
  const raw = (req.value.response_text || '').trim()
  if (!/^[[{]/.test(raw)) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return ''
  }
})
</script>

<template>
  <article class="min-w-0">
    <!-- Who and what -->
    <header class="mb-5 flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div class="min-w-0 flex-1 basis-64">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <ModalityBadge :type="type" />
          <VisibilityBadge v-if="req.is_owner && req.visibility" :visibility="req.visibility" />
          <Badge v-if="failed" variant="destructive">{{ statusLabel(req.status) }}</Badge>
          <Badge v-else-if="running" variant="secondary" class="gap-1">
            <Loader2 class="size-3 animate-spin" /> {{ statusLabel(req.status) }}
          </Badge>
        </div>
        <h1 class="text-xl font-semibold leading-snug tracking-tight break-words sm:text-2xl" data-testid="request-title">
          {{ title }}
        </h1>
        <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          <NuxtLink
            v-if="owner"
            :to="`/${owner}`"
            class="inline-flex min-w-0 items-center gap-1.5 font-medium text-foreground hover:underline"
          >
            <img
              v-if="req.github_login"
              :src="`https://github.com/${req.github_login}.png?size=48`"
              alt=""
              class="size-5 shrink-0 rounded-full border"
              loading="lazy"
            />
            <span class="truncate">@{{ owner }}</span>
          </NuxtLink>
          <span v-if="owner" aria-hidden="true">·</span>
          <time :datetime="req.created_on" :title="formatAbsolute(req.created_on)">
            {{ formatRelative(req.created_on) }}
          </time>
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-1.5">
        <slot name="actions" />
      </div>
    </header>

    <!-- The result -->
    <section class="mb-4" data-testid="request-result">
      <!-- Images -->
      <template v-if="type === 'IMAGE'">
        <ImageGenMedia v-if="req.image_urls?.length" :inputs="inputImages" :outputs="req.image_urls" />
        <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
      </template>

      <!-- Song -->
      <div
        v-else-if="type === 'MUSIC'"
        class="flex flex-col gap-4 overflow-hidden rounded-2xl border bg-gradient-to-br from-fuchsia-500/10 via-transparent to-transparent p-4 sm:flex-row sm:items-center sm:gap-6 sm:p-5"
      >
        <button
          v-if="req.cover_image_url"
          type="button"
          class="mx-auto w-full max-w-[14rem] shrink-0 cursor-zoom-in sm:mx-0 sm:w-48"
          :aria-label="t('request.openImage')"
          @click="lightbox.open(req.cover_image_url)"
        >
          <img :src="req.cover_image_url" :alt="title" class="aspect-square w-full rounded-xl border object-cover shadow-md" />
        </button>
        <div class="min-w-0 flex-1">
          <template v-if="track">
            <div class="flex items-center gap-3">
              <button
                type="button"
                class="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow transition hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                :aria-label="songPlaying ? t('request.pause') : t('request.play')"
                data-testid="request-play"
                @click="toggleSong"
              >
                <Pause v-if="songPlaying" class="size-6" />
                <Play v-else class="size-6 translate-x-0.5" />
              </button>
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ track.title }}</p>
                <p class="text-sm tabular-nums text-muted-foreground">
                  <template v-if="isCurrent">{{ formatTrackTime(player.currentTime) }} / </template>{{ formatTrackTime(req.audio_seconds) }}
                </p>
              </div>
              <a
                :href="req.output_audio_url || undefined"
                download
                class="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
                :aria-label="t('request.download')"
                :title="t('request.download')"
              >
                <Download class="size-4" />
              </a>
            </div>
            <div class="mt-3 h-1 overflow-hidden rounded-full bg-foreground/10">
              <div class="h-full rounded-full bg-primary transition-[width]" :style="{ width: `${songPct}%` }" />
            </div>
          </template>
          <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
        </div>
      </div>

      <!-- Video -->
      <template v-else-if="type === 'VIDEO'">
        <video
          v-if="req.video_url"
          :src="req.video_url"
          :poster="req.input_image_url || undefined"
          controls
          loop
          playsinline
          preload="metadata"
          class="max-h-[75vh] w-full rounded-2xl border bg-black object-contain"
        />
        <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
      </template>

      <!-- 3D model -->
      <template v-else-if="type === 'MESH'">
        <div v-if="req.model_url" class="relative">
          <ModelViewer
            :src="req.model_url"
            :poster-src="req.input_image_url"
            :alt="title"
            :download-name="`inference-club-${req.public_id || req.id}.glb`"
          />
          <Button
            variant="secondary"
            size="sm"
            class="absolute right-3 top-3 gap-2 shadow"
            :disabled="downloading"
            @click="download(req.model_url, `inference-club-${req.public_id || req.id}.glb`)"
          >
            <component :is="downloading ? Loader2 : Download" class="size-4" :class="downloading ? 'animate-spin' : ''" />
            .glb
          </Button>
        </div>
        <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
      </template>

      <!-- Speech -->
      <template v-else-if="type === 'TTS'">
        <AudioClip
          v-if="req.output_audio_url"
          :src="req.output_audio_url"
          :seconds="req.audio_seconds"
          :download-name="`inference-club-${req.public_id || req.id}`"
        />
        <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
      </template>

      <!-- Transcription -->
      <div v-else-if="type === 'STT'" class="rounded-2xl border p-4">
        <TranscriptView
          :text="req.response_text || ''"
          :src="req.audio_url"
          :words="req.transcription?.words"
          :segments="req.transcription?.segments"
          :language="req.transcription?.language"
        />
      </div>

      <!-- Audio clean-up: before and after -->
      <div v-else-if="type === 'ENHANCE'" class="grid gap-3 sm:grid-cols-2">
        <AudioClip v-if="req.audio_url" :src="req.audio_url" :label="t('request.original')" />
        <AudioClip
          v-if="req.output_audio_url"
          :src="req.output_audio_url"
          :seconds="req.audio_seconds"
          :label="t('request.enhanced')"
          :download-name="`inference-club-${req.public_id || req.id}`"
        />
        <p v-if="!req.output_audio_url" class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.nothingStored') }}</p>
      </div>

      <!-- Chat: the answer leads -->
      <template v-else>
        <pre
          v-if="answerJson"
          class="overflow-x-auto rounded-2xl border bg-card p-4 text-xs leading-relaxed sm:p-5 sm:text-sm"
        >{{ answerJson }}</pre>
        <div v-else-if="req.response_text" class="rounded-2xl border bg-card p-4 sm:p-5">
          <MarkdownRenderer :content="req.response_text" />
        </div>
        <p v-else class="rounded-2xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{{ failed ? t('request.failed') : t('request.noAnswer') }}</p>
        <details v-if="req.reasoning" class="group mt-3 rounded-xl border border-amber-500/25 bg-amber-500/5">
          <summary class="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-sm font-medium">
            <Brain class="size-4 text-amber-500" /> {{ t('request.thinking') }}
            <ChevronDown class="ml-auto size-4 transition-transform group-open:rotate-180" />
          </summary>
          <div class="px-4 pb-4 text-sm text-muted-foreground">
            <MarkdownRenderer :content="req.reasoning" />
          </div>
        </details>
      </template>
    </section>

    <!-- Who made it, on what, how fast -->
    <dl
      v-if="facts.length"
      class="mb-4 flex flex-wrap gap-px overflow-hidden rounded-2xl border bg-border"
      data-testid="request-facts"
    >
      <div v-for="f in facts" :key="f.key + f.value" class="min-w-0 flex-1 basis-[9.5rem] bg-card px-3 py-2.5 sm:basis-44">
        <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          <component :is="FACT_ICONS[f.key]" class="size-3 shrink-0" />
          <span class="truncate">{{ t(`request.facts.${f.key}`) }}</span>
        </dt>
        <dd class="mt-0.5 flex min-w-0 items-baseline gap-1.5">
          <component
            :is="f.to ? 'NuxtLink' : 'span'"
            :to="f.to || undefined"
            class="truncate text-sm font-semibold tabular-nums"
            :class="f.to ? 'hover:underline' : ''"
            :title="f.value"
          >{{ f.value }}</component>
          <span v-if="f.hint" class="shrink-0 text-xs text-muted-foreground">{{ f.hint }}</span>
        </dd>
      </div>
    </dl>

    <!-- What was asked for -->
    <section
      v-if="prompt || sourceName || lyrics || negative || inputImages.length || settings.main.length || (type === 'LLM' && messages.length)"
      class="mb-4 rounded-2xl border p-4 sm:p-5"
      data-testid="request-inputs"
    >
      <h2 class="mb-3 text-sm font-semibold">{{ t('request.inputs') }}</h2>

      <!-- Chat: the conversation that led to the answer -->
      <div v-if="type === 'LLM' && messages.length" class="space-y-2.5">
        <template v-for="(m, i) in messages" :key="i">
          <details v-if="m.role === 'system'" class="group rounded-lg border bg-muted/30">
            <summary class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground">
              {{ t('request.systemPrompt') }}
              <ChevronDown class="ml-auto size-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div class="px-3 pb-3 text-sm"><MarkdownRenderer :content="m.content" /></div>
          </details>
          <div v-else class="min-w-0 rounded-lg border p-3" :class="m.role === 'user' ? 'bg-primary/5' : ''">
            <span class="mb-1.5 inline-flex rounded-md border px-1.5 py-px text-[11px] font-medium capitalize" :class="roleClasses(m.role)">
              {{ m.role || 'message' }}
            </span>
            <div v-if="m.media?.length" class="mb-2 flex flex-wrap gap-2">
              <template v-for="(media, mi) in m.media" :key="mi">
                <img
                  v-if="media.kind === 'image'"
                  :src="media.url"
                  alt=""
                  class="max-h-40 max-w-full cursor-zoom-in rounded-md border object-contain"
                  @click="lightbox.open(media.url)"
                />
                <video v-else-if="media.kind === 'video'" :src="media.url" controls class="max-h-56 max-w-full rounded-md border" />
                <AudioClip v-else :src="media.url" class="w-full" />
              </template>
            </div>
            <MarkdownRenderer :content="m.content" />
          </div>
        </template>
      </div>

      <!-- Everything else: the prompt in the person's words -->
      <div v-else-if="prompt" class="group/prompt relative rounded-lg bg-muted/40 p-3 pr-10">
        <p class="whitespace-pre-wrap break-words text-sm leading-relaxed" data-testid="request-prompt">{{ prompt }}</p>
        <button
          type="button"
          class="absolute right-1.5 top-1.5 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          :aria-label="t('request.copyPrompt')"
          :title="t('request.copyPrompt')"
          @click="copyPrompt"
        >
          <Check v-if="copied" class="size-4 text-emerald-500" />
          <Copy v-else class="size-4" />
        </button>
      </div>

      <ImageRevisedPrompt v-if="type === 'IMAGE'" :meta="req.image" class="mt-3" />

      <p v-if="negative" class="mt-3 text-sm break-words">
        <span class="text-muted-foreground">{{ t('request.negative') }}</span> {{ negative }}
      </p>

      <div v-if="sourceName || (inputImages.length && type !== 'IMAGE')" class="mt-3 flex flex-wrap items-center gap-2">
        <button
          v-for="(src, i) in type !== 'IMAGE' ? inputImages : []"
          :key="src"
          type="button"
          class="cursor-zoom-in"
          :aria-label="t('request.openImage')"
          @click="lightbox.openList(inputImages, i)"
        >
          <img :src="src" alt="" class="size-16 rounded-lg border object-cover" loading="lazy" />
        </button>
        <span v-if="sourceName" class="inline-flex min-w-0 items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs">
          <component :is="['STT', 'ENHANCE'].includes(type) ? FileAudio : FileImage" class="size-3.5 shrink-0 text-muted-foreground" />
          <span class="truncate">{{ sourceName }}</span>
        </span>
      </div>

      <details v-if="lyrics" class="group mt-3 rounded-lg border" open>
        <summary class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground">
          {{ t('request.lyrics') }}
          <ChevronDown class="ml-auto size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <pre class="whitespace-pre-wrap break-words px-3 pb-3 font-sans text-sm leading-relaxed">{{ lyrics }}</pre>
      </details>

      <ul v-if="settings.main.length" class="mt-3 flex flex-wrap gap-1.5" data-testid="request-settings">
        <li
          v-for="s in settings.main"
          :key="s.key"
          class="inline-flex max-w-full items-baseline gap-1.5 rounded-full border bg-background px-2.5 py-1 text-xs"
        >
          <span class="shrink-0 text-muted-foreground">{{ t(`request.settings.${s.key}`) }}</span>
          <span class="truncate font-medium tabular-nums">{{ s.value }}</span>
        </li>
      </ul>
    </section>

    <!-- The rest, for the curious -->
    <details class="group rounded-2xl border" data-testid="request-details">
      <summary class="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
        {{ t('request.allDetails') }}
        <ChevronDown class="ml-auto size-4 transition-transform group-open:rotate-180" />
      </summary>
      <div class="space-y-4 border-t px-4 py-4">
        <dl class="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 text-muted-foreground">{{ t('request.details.id') }}</dt>
            <dd class="truncate font-mono text-xs">{{ req.public_id || req.id }}</dd>
          </div>
          <div class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 text-muted-foreground">{{ t('request.details.status') }}</dt>
            <dd class="truncate">{{ statusLabel(req.status) }}<template v-if="req.streamed"> · {{ t('request.details.streamed') }}</template></dd>
          </div>
          <div v-if="finishReason" class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 text-muted-foreground">{{ t('request.details.finish') }}</dt>
            <dd class="truncate">{{ finishReason }}</dd>
          </div>
          <div class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 text-muted-foreground">{{ t('request.details.created') }}</dt>
            <dd class="truncate">{{ formatAbsolute(req.created_on) }}</dd>
          </div>
          <div class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 text-muted-foreground">{{ t('request.details.updated') }}</dt>
            <dd class="truncate">{{ formatAbsolute(req.modified_on) }}</dd>
          </div>
          <div v-for="s in settings.rest" :key="s.key" class="flex min-w-0 justify-between gap-3">
            <dt class="shrink-0 font-mono text-xs text-muted-foreground">{{ s.key }}</dt>
            <dd class="truncate font-mono text-xs" :title="s.value">{{ s.value }}</dd>
          </div>
        </dl>
        <template v-if="req.is_owner">
          <details class="rounded-lg border bg-muted/30">
            <summary class="cursor-pointer px-3 py-2 text-xs font-medium">{{ t('request.details.rawRequest') }}</summary>
            <pre class="overflow-x-auto rounded-b-lg bg-zinc-950 p-3 text-xs text-zinc-100">{{ pretty(req.payload) }}</pre>
          </details>
          <details class="rounded-lg border bg-muted/30">
            <summary class="cursor-pointer px-3 py-2 text-xs font-medium">{{ t('request.details.rawResult') }}</summary>
            <pre class="overflow-x-auto rounded-b-lg bg-zinc-950 p-3 text-xs text-zinc-100">{{ pretty(req.results) }}</pre>
          </details>
        </template>
      </div>
    </details>
  </article>
</template>

<style scoped>
summary::-webkit-details-marker {
  display: none;
}
</style>
