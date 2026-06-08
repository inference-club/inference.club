<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Cpu, Server, Zap, Clock, Trash2, MessageSquare, Radio, ArrowRight, Brain, Github, AudioLines, Image as ImageIcon, Box,
} from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { statusVariant, formatRelative, formatLatency, totalTokens } from '@/utils/inference'

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

const emit = defineEmits<{ (e: 'delete', id: string): void }>()

const lightbox = useImageLightbox()
const isStt = computed(() => props.request.inference_type === 'STT')
const isImage = computed(() => props.request.inference_type === 'IMAGE')
const isTts = computed(() => props.request.inference_type === 'TTS')
const isMesh = computed(() => props.request.inference_type === 'MESH')
const fmtSeconds = (s?: number | null) =>
  s == null ? null : s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`

const onClick = () => {
  if (props.linkable) navigateTo(`/dashboard/inference/requests/${props.request.id}`)
}

// Local copy of the visibility so the badge updates instantly when the owner
// edits it via the action bar (without mutating the request prop).
const displayVisibility = ref<Visibility | undefined>(props.request.visibility)
watch(() => props.request.visibility, (v) => { displayVisibility.value = v })
</script>

<template>
  <Card
    class="p-4 transition-colors group"
    :class="linkable ? 'hover:border-primary/50 hover:bg-accent/30 cursor-pointer' : ''"
    @click="onClick"
  >
    <!-- Header: badges + delete -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-center gap-2 flex-wrap">
        <Badge variant="outline">{{ props.request.inference_type }}</Badge>
        <Badge :variant="statusVariant(props.request.status)">{{ props.request.status }}</Badge>
        <Badge v-if="props.request.model_name" variant="secondary" class="font-mono">
          <Cpu class="size-3" /> {{ props.request.model_name }}
        </Badge>
        <Badge v-if="props.request.provider" variant="outline">
          <Server class="size-3" /> {{ props.request.provider.name }}
        </Badge>
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
          @visibility-change="(v) => (displayVisibility = v)"
        />

        <AlertDialog v-if="props.linkable && props.request.is_owner">
        <AlertDialogTrigger as-child @click.stop>
          <Button
            variant="ghost"
            size="icon"
            class="size-8 text-muted-foreground hover:text-destructive shrink-0"
            :disabled="deleting"
            aria-label="Delete request"
          >
            <Trash2 class="size-4" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent @click.stop>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes request #{{ props.request.id }} and its stored
              prompt and response. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              class="bg-destructive text-white hover:bg-destructive/90"
              @click="emit('delete', String(props.request.id))"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      </div>
    </div>

    <!-- Body: input on the left, output on the right -->
    <!-- STT: input audio → transcript -->
    <div v-if="isStt" class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Audio</p>
        <audio v-if="props.request.audio_url" :src="props.request.audio_url" controls class="w-full h-9" @click.stop />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
      <div class="min-w-0">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Transcript</p>
        <p class="text-sm line-clamp-3">{{ props.request.response_preview || '—' }}</p>
      </div>
    </div>

    <!-- TTS: input text → audio output -->
    <div v-else-if="isTts" class="mt-3 grid gap-4 sm:grid-cols-2">
      <div class="min-w-0">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Text</p>
        <p class="text-sm line-clamp-3">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div class="min-w-0">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Speech</p>
        <audio
          v-if="props.request.output_audio_url"
          :src="props.request.output_audio_url"
          controls
          class="w-full h-9"
          @click.stop
        />
        <p v-else class="text-sm text-muted-foreground">—</p>
      </div>
    </div>

    <!-- IMAGE: prompt → generated images (images feature large on the right) -->
    <div v-else-if="isImage" class="mt-3 grid gap-4 sm:grid-cols-2 sm:items-stretch">
      <div class="min-w-0 flex flex-col">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Prompt</p>
        <p class="text-sm line-clamp-[8]">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div
        v-if="props.request.image_urls?.length"
        class="grid gap-1.5"
        :class="props.request.image_urls.length === 1 ? 'grid-cols-1' : 'grid-cols-2'"
      >
        <img
          v-for="(url, i) in props.request.image_urls.slice(0, 4)"
          :key="i"
          :src="url"
          class="h-full max-h-80 min-h-32 w-full cursor-zoom-in rounded-lg border object-cover transition-opacity hover:opacity-90"
          loading="lazy"
          @click.stop="lightbox.open(url)"
        />
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
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Prompt</p>
        <p class="text-sm line-clamp-3">{{ props.request.prompt_preview || '—' }}</p>
      </div>
      <div class="min-w-0">
        <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Response</p>
        <p class="text-sm text-muted-foreground line-clamp-3">{{ props.request.response_preview || '—' }}</p>
      </div>
    </div>

    <!-- Footer metadata -->
    <div class="mt-3 pt-3 border-t flex items-center gap-4 flex-wrap text-xs text-muted-foreground">
      <span
        v-if="isStt || isTts"
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
      </template>
      <span class="inline-flex items-center gap-1" title="Latency">
        <Clock class="size-3.5" /> {{ formatLatency(props.request.latency_ms) }}
      </span>
      <span class="ml-auto inline-flex items-center gap-1" :class="linkable ? 'group-hover:text-foreground' : ''">
        {{ formatRelative(props.request.created_on) }}
        <ArrowRight v-if="linkable" class="size-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </span>
    </div>
  </Card>
</template>
