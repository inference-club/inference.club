<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Cpu, Server, Zap, Clock, MessageSquare, Radio, ArrowRight, Brain, Github, AudioLines, Image as ImageIcon, Box, Clapperboard, Star, Gauge, Timer, Play, Pause, ListPlus, Music, Waves, HardDrive,
} from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { statusVariant, statusLabel, formatRelative, formatLatency, totalTokens, nodeUrl } from '@/utils/inference'
import { prettyGpuModel } from '@/composables/useMachineForm'
import { usePlayerStore } from '@/stores/player'
import { trackFromRequest, formatTrackTime } from '@/utils/player'

const props = withDefaults(
  defineProps<{
    request: InferenceRequest
    showOwner?: boolean
    deleting?: boolean
    // When false the card is display-only: no click-through to the (auth-gated)
    // detail page, no delete button. Used on the public profile.
    linkable?: boolean
    // Show the star / bookmark / share / owner-menu action bar in the header.
    actions?: boolean
  }>(),
  { linkable: true, actions: true },
)

const emit = defineEmits<{ (e: 'delete' | 'retried', id: string): void }>()

// Defer audio/video network activity (metadata range requests, poster
// fetches) until the card is near the viewport. <img> gets this natively
// via loading="lazy"; media elements don't, and a list of music/video cards
// would otherwise hit storage for every mounted card on page load.
const mediaEl = ref<HTMLElement | null>(null)
const mediaInView = useInView(mediaEl)
const whenInView = (url?: string | null) => (mediaInView.value && url) || undefined

const isStt = computed(() => props.request.inference_type === 'STT')
const isImage = computed(() => props.request.inference_type === 'IMAGE')
// Source image(s) for an edit: prefer the plural list, fall back to the single.
const imageInputs = computed(() =>
  props.request.input_image_urls?.length
    ? props.request.input_image_urls
    : props.request.input_image_url
      ? [props.request.input_image_url]
      : [],
)
// VOICE (Dia voice cloning) renders like TTS: input script → audio output.
const isTts = computed(
  () => props.request.inference_type === 'TTS' || props.request.inference_type === 'VOICE',
)
const isMesh = computed(() => props.request.inference_type === 'MESH')
const isMusic = computed(() => props.request.inference_type === 'MUSIC')
const isVideo = computed(() => props.request.inference_type === 'VIDEO')
// ENHANCE (StudioVoice): original audio in → cleaned audio out.
const isEnhance = computed(() => props.request.inference_type === 'ENHANCE')
const fmtSeconds = (s?: number | null) =>
  s == null ? null : s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`

// Success is the quiet default — only abnormal states earn a badge.
const showStatus = computed(
  () => props.request.status !== 'PROCESSED' && props.request.status !== 'SAVED',
)

const onClick = () => {
  if (props.linkable) {
    // Prefer the opaque public_id so the URL never exposes the sequential PK.
    const ref = props.request.public_id || props.request.id
    navigateTo(`/dashboard/inference/requests/${ref}`)
  }
}

// Local copy of the visibility so the badge updates instantly when the owner
// edits it via the action bar (without mutating the request prop).
const displayVisibility = ref<Visibility | undefined>(props.request.visibility)
watch(() => props.request.visibility, (v) => { displayVisibility.value = v })

// MUSIC plays through the global player (Spotify-style bottom bar) instead of
// a per-card <audio>; STT/TTS keep native players — they're utterances, not
// tracks.
const player = usePlayerStore()
const track = computed(() => trackFromRequest(props.request))
const isCurrentTrack = computed(
  () => !!track.value && player.current?.id === track.value.id,
)
const playPauseTrack = () => {
  if (!track.value) return
  if (isCurrentTrack.value) player.toggle()
  else player.playTrack(track.value)
}
const queueTrack = () => {
  if (track.value) player.addToQueue([track.value])
}

// "Where it ran" — the node link + its GPUs, shown as clickable chips.
const nodeHref = computed(() => nodeUrl(props.request))
const hostGpus = computed(() => props.request.host?.gpus || [])
const hostLabel = computed(
  () => props.request.host?.hostname || props.request.host?.host_id || '',
)
</script>

<template>
  <Card
    class="p-4 transition-colors group min-w-0"
    :class="linkable ? 'hover:border-primary/50 hover:bg-accent/30 cursor-pointer' : ''"
    @click="onClick"
  >
    <!-- Header: badges + delete -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2 flex-wrap">
        <ModalityBadge :type="props.request.inference_type" />
        <Badge v-if="showStatus" :variant="statusVariant(props.request.status)">
          {{ statusLabel(props.request.status) }}
        </Badge>
        <Badge
          v-if="props.request.model_name"
          variant="secondary"
          class="max-w-[11rem] sm:max-w-[16rem] font-mono"
          :title="props.request.model_name"
        >
          <Cpu class="size-3 shrink-0" />
          <span class="min-w-0 truncate">{{ props.request.model_name }}</span>
        </Badge>
        <NuxtLink
          v-if="props.request.provider?.owner_handle"
          :to="`/${props.request.provider.owner_handle}`"
          @click.stop
        >
          <Badge variant="outline" class="cursor-pointer hover:bg-accent">
            <Server class="size-3" /> {{ props.request.provider.name }}
          </Badge>
        </NuxtLink>
        <Badge v-else-if="props.request.provider" variant="outline">
          <Server class="size-3" /> {{ props.request.provider.name }}
        </Badge>

        <!-- Where it ran: the host node + its GPU(s), linking to the node page. -->
        <NuxtLink v-if="hostLabel && nodeHref" :to="nodeHref" @click.stop>
          <Badge variant="outline" class="cursor-pointer font-mono hover:bg-accent" :title="props.request.host?.host_id || ''">
            <HardDrive class="size-3" /> {{ hostLabel }}
          </Badge>
        </NuxtLink>
        <Badge v-else-if="hostLabel" variant="outline" class="font-mono">
          <HardDrive class="size-3" /> {{ hostLabel }}
        </Badge>
        <component
          :is="nodeHref ? 'NuxtLink' : 'span'"
          v-for="g in hostGpus"
          :key="g.index"
          :to="nodeHref ? `${nodeHref}#gpu-${g.index}` : undefined"
          @click.stop
        >
          <Badge variant="secondary" class="font-mono" :class="nodeHref ? 'cursor-pointer hover:bg-accent' : ''">
            <Cpu class="size-3" /> {{ prettyGpuModel(g.model || '') || g.model }}
          </Badge>
        </component>

        <Badge v-if="props.request.streamed" variant="outline" class="text-sky-600 dark:text-sky-400">
          <Radio class="size-3" /> streamed
        </Badge>
        <Badge v-if="props.request.has_reasoning" variant="outline" class="text-amber-600 dark:text-amber-400">
          <Brain class="size-3" /> thinking
        </Badge>
        <Badge v-if="showOwner" variant="outline" class="font-mono">
          <Github class="size-3" /> {{ props.request.github_login || props.request.owner }}
        </Badge>
        <VisibilityBadge
          v-if="displayVisibility && (props.request.is_owner || displayVisibility !== 'PUBLIC')"
          :visibility="displayVisibility"
        />
      </div>

      <div class="flex items-center gap-0.5 shrink-0">
        <RequestActionBar
          v-if="actions"
          :request="props.request"
          dense
          :can-delete="props.linkable && props.request.is_owner"
          :deleting="deleting"
          @visibility-change="(v) => (displayVisibility = v)"
          @retried="emit('retried', String(props.request.id))"
          @delete="emit('delete', String(props.request.id))"
        />
      </div>
    </div>

    <!-- Body: input on the left, output on the right -->
    <!-- STT: input audio → transcript -->
    <div v-if="isStt" ref="mediaEl" class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Audio</p>
        <audio
          v-if="props.request.audio_url"
          :src="whenInView(props.request.audio_url)"
          preload="metadata"
          controls
          class="w-full h-9"
          @click.stop
        />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Transcript</p>
        <p class="text-sm break-words line-clamp-3">{{ props.request.response_preview || '—' }}</p>
      </div>
    </div>

    <!-- TTS: input text → audio output -->
    <div v-else-if="isTts" ref="mediaEl" class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Text</p>
        <p class="text-sm break-words line-clamp-3">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Speech</p>
        <audio
          v-if="props.request.output_audio_url"
          :src="whenInView(props.request.output_audio_url)"
          preload="metadata"
          controls
          class="w-full h-9"
          @click.stop
        />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
    </div>

    <!-- ENHANCE: original audio → cleaned audio -->
    <div v-else-if="isEnhance" ref="mediaEl" class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Original</p>
        <audio
          v-if="props.request.audio_url"
          :src="whenInView(props.request.audio_url)"
          preload="metadata"
          controls
          class="w-full h-9"
          @click.stop
        />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5 flex items-center gap-1">
          <Waves class="size-3 text-cyan-500" /> Enhanced
        </p>
        <audio
          v-if="props.request.output_audio_url"
          :src="whenInView(props.request.output_audio_url)"
          preload="metadata"
          controls
          class="w-full h-9"
          @click.stop
        />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
    </div>

    <!-- MUSIC: a tight track row — cover (with play overlay) + prompt-as-title +
         duration, plays through the global player bar. -->
    <div v-else-if="isMusic" ref="mediaEl" class="mt-3">
      <div v-if="track" class="flex items-center gap-3" @click.stop>
        <!-- Cover doubles as the play/pause control -->
        <button
          type="button"
          class="group/cover relative size-14 shrink-0 overflow-hidden rounded-lg border"
          :title="isCurrentTrack && player.playing ? 'Pause' : 'Play'"
          data-testid="card-play-track"
          @click="playPauseTrack"
        >
          <img
            v-if="track.coverUrl"
            :src="track.coverUrl"
            class="size-full object-cover"
            :alt="track.title"
            loading="lazy"
          />
          <div v-else class="flex size-full items-center justify-center bg-gradient-to-br from-primary/25 to-primary/[0.04]">
            <Music class="size-6 text-primary/70" />
          </div>
          <!-- Always-visible play affordance (no hover on touch); the scrim
               darkens on hover / while playing. -->
          <span
            class="absolute inset-0 flex items-center justify-center text-white drop-shadow transition-colors"
            :class="isCurrentTrack && player.playing ? 'bg-black/45' : 'bg-black/20 group-hover/cover:bg-black/45'"
          >
            <Pause v-if="isCurrentTrack && player.playing" class="size-6" />
            <Play v-else class="size-6 translate-x-px" />
          </span>
        </button>

        <!-- Title (the prompt) + now-playing / duration line -->
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium" :title="props.request.prompt_preview || ''">
            {{ props.request.prompt_preview || 'Untitled track' }}
          </p>
          <div class="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <span v-if="isCurrentTrack && player.playing" class="eq" aria-hidden="true">
              <i /><i /><i /><i />
            </span>
            <AudioLines v-else class="size-3.5 shrink-0" />
            <span class="tabular-nums">{{ formatTrackTime(track.duration) }}</span>
          </div>
        </div>

        <!-- Add to queue -->
        <Button
          variant="ghost"
          size="icon"
          class="size-9 shrink-0 text-muted-foreground"
          title="Add to queue"
          @click="queueTrack"
        >
          <ListPlus class="size-4" />
        </Button>
      </div>
      <p v-else class="text-sm break-words line-clamp-2 text-muted-foreground">
        {{ props.request.prompt_preview || '—' }}
      </p>
    </div>

    <!-- IMAGE: prompt → generated images (images feature large on the right) -->
    <div v-else-if="isImage" class="mt-3 grid gap-4 sm:grid-cols-2 sm:items-stretch">
      <div class="min-w-0 flex flex-col">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Prompt</p>
        <p class="text-sm break-words line-clamp-[8]">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div v-if="imageInputs.length || props.request.image_urls?.length" @click.stop>
        <ImageGenMedia
          :inputs="imageInputs"
          :outputs="props.request.image_urls"
          compact
        />
      </div>
      <p v-else class="text-sm text-muted-foreground">—</p>
    </div>

    <!-- VIDEO: prompt (+ optional first frame) → generated video -->
    <div v-else-if="isVideo" ref="mediaEl" class="mt-3 grid gap-4 sm:grid-cols-2 sm:items-stretch">
      <div class="min-w-0 flex flex-col">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Prompt</p>
        <p class="text-sm break-words line-clamp-[8]">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div v-if="props.request.video_url" class="relative" @click.stop>
        <video
          :src="whenInView(props.request.video_url)"
          :poster="whenInView(props.request.input_image_url)"
          controls
          loop
          playsinline
          preload="metadata"
          class="max-h-80 w-full rounded-lg border bg-black object-contain"
        />
        <NuxtLink
          v-if="linkable"
          :to="`/dashboard/watch/${props.request.id}`"
          class="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-black/60 px-2 py-1 text-xs text-white backdrop-blur hover:bg-black/80"
          title="Open in the watch page"
        >
          <Clapperboard class="size-3.5" /> Watch
        </NuxtLink>
      </div>
      <p v-else class="text-sm text-muted-foreground">—</p>
    </div>

    <!-- MESH: input image → interactive 3D model (lazy-mounted in feeds) -->
    <div v-else-if="isMesh" class="mt-3">
      <ModelViewer
        v-if="props.request.model_url"
        :src="props.request.model_url"
        :poster-src="props.request.input_image_url"
        :lazy="true"
        :downloadable="false"
        alt="Generated 3D model"
        @click.stop
      />
      <p v-else class="text-sm text-muted-foreground">—</p>
    </div>

    <!-- LLM: prompt → response -->
    <div v-else class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Prompt</p>
        <p class="text-sm break-words line-clamp-3">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div class="min-w-0">
        <p class="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">Response</p>
        <p class="text-sm text-muted-foreground break-words line-clamp-3">{{ props.request.response_preview || '—' }}</p>
      </div>
    </div>

    <!-- Footer metadata -->
    <div class="mt-3 pt-3 border-t flex items-center gap-4 flex-wrap text-xs text-muted-foreground">
      <span
        v-if="isStt || isTts || isMusic || isEnhance"
        class="inline-flex items-center gap-1"
        title="Audio duration"
      >
        <AudioLines class="size-3.5" /> {{ fmtSeconds(props.request.audio_seconds) ?? '—' }} audio
      </span>
      <span
        v-else-if="isImage"
        class="inline-flex items-center gap-1"
        title="Images generated"
      >
        <ImageIcon class="size-3.5" /> {{ props.request.image_count ?? 0 }} image{{ (props.request.image_count ?? 0) === 1 ? '' : 's' }}
      </span>
      <span
        v-else-if="isVideo"
        class="inline-flex items-center gap-1"
        title="Video duration"
      >
        <Clapperboard class="size-3.5" />
        {{ fmtSeconds(props.request.video?.seconds ?? props.request.audio_seconds) ?? '—' }}
        <template v-if="props.request.video?.width && props.request.video?.height">
          · {{ props.request.video.width }}×{{ props.request.video.height }}
        </template>
      </span>
      <span
        v-else-if="isMesh && props.request.mesh"
        class="inline-flex items-center gap-1"
        title="Mesh geometry"
      >
        <Box class="size-3.5" />
        {{ (props.request.mesh.vertices ?? 0).toLocaleString() }} verts ·
        {{ (props.request.mesh.faces ?? 0).toLocaleString() }} faces
      </span>
      <template v-else>
        <span class="inline-flex items-center gap-1" title="Messages in this request">
          <MessageSquare class="size-3.5" /> {{ props.request.message_count ?? 0 }} msg
        </span>
        <span v-if="totalTokens(props.request) !== null" class="inline-flex items-center gap-1" title="Token usage">
          <Zap class="size-3.5" /> {{ totalTokens(props.request) }} tok
          <template v-if="props.request.usage">
            ({{ props.request.usage.prompt_tokens ?? '?' }} in / {{ props.request.usage.completion_tokens ?? '?' }} out)
          </template>
        </span>
        <span
          v-if="props.request.tokens_per_second"
          class="inline-flex items-center gap-1"
          title="Decode speed"
        >
          <Gauge class="size-3.5" /> {{ Math.round(props.request.tokens_per_second) }} tok/s
        </span>
        <span
          v-if="props.request.ttft_ms"
          class="inline-flex items-center gap-1"
          title="Time to first token"
        >
          <Timer class="size-3.5" /> {{ formatLatency(props.request.ttft_ms) }} TTFT
        </span>
      </template>
      <span class="inline-flex items-center gap-1" title="Latency">
        <Clock class="size-3.5" /> {{ formatLatency(props.request.latency_ms) }}
      </span>
      <span
        v-if="props.request.star_count"
        class="inline-flex items-center gap-1"
        title="Stars"
      >
        <Star class="size-3.5" /> {{ props.request.star_count }}
      </span>
      <span class="ml-auto inline-flex items-center gap-1" :class="linkable ? 'group-hover:text-foreground' : ''">
        {{ formatRelative(props.request.created_on) }}
        <ArrowRight v-if="linkable" class="size-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </span>
    </div>
  </Card>
</template>

<style scoped>
/* Tiny "now playing" equalizer for the music track row. */
.eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 1px;
  height: 0.75rem;
}
.eq i {
  width: 2px;
  background: var(--primary);
  border-radius: 1px;
  animation: eq 0.9s ease-in-out infinite;
}
.eq i:nth-child(1) { height: 40%; animation-delay: -0.2s; }
.eq i:nth-child(2) { height: 90%; animation-delay: -0.5s; }
.eq i:nth-child(3) { height: 60%; animation-delay: -0.1s; }
.eq i:nth-child(4) { height: 80%; animation-delay: -0.35s; }
@keyframes eq {
  0%, 100% { transform: scaleY(0.4); }
  50% { transform: scaleY(1); }
}
@media (prefers-reduced-motion: reduce) {
  .eq i { animation: none; }
}
</style>
