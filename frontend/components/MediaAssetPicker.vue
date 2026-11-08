<script setup lang="ts">
// Pick an earlier generation's audio or video as an input (LTX-2.5 audio-to-
// video, video-to-video, retake). Emits an asset reference (`asset:<id>`) —
// the backend inlines the bytes and records provenance — so a song from
// ACE-Step, a Dia voice or a previous video chains straight into a new one.
import { Loader2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { InferenceRequest } from '@/types'

const props = defineProps<{ open: boolean; kind: 'audio' | 'video' }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'select', payload: { ref: string; url: string; label: string; type: string }): void
}>()

const { listInferenceRequests } = useInferenceRequest()

// Which request types carry a usable output of each kind.
const TYPES: Record<'audio' | 'video', string[]> = {
  audio: ['MUSIC', 'VOICE', 'TTS'],
  video: ['VIDEO'],
}

interface Item { ref: string; url: string; label: string; type: string; id: number }
const items = ref<Item[]>([])
const loading = ref(false)
const error = ref('')

const assetId = (url?: string | null) => url?.match(/\/assets\/([^/?#]+)/)?.[1] ?? null

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const pages = await Promise.all(
      TYPES[props.kind].map((type) => listInferenceRequests(24, 0, { type }).catch(() => ({ results: [] }))),
    )
    const all = pages.flatMap((p) => (p as { results: InferenceRequest[] }).results)
    items.value = all
      .map((r) => {
        const url = props.kind === 'video' ? r.video_url : r.output_audio_url
        const id = assetId(url)
        return id && url
          ? { ref: `asset:${id}`, url, label: r.prompt_preview || r.model_name || `#${r.id}`,
              type: r.inference_type, id: r.id }
          : null
      })
      .filter((x): x is Item => !!x)
      .sort((a, b) => b.id - a.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load your generations'
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (o) => { if (o) load() }, { immediate: true })

const pick = (it: Item) => {
  emit('select', { ref: it.ref, url: it.url, label: it.label, type: it.type })
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="max-w-3xl max-h-[80vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Use {{ kind === 'video' ? 'a video' : 'audio' }} from your generations</DialogTitle>
      </DialogHeader>
      <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground py-6">
        <Loader2 class="h-4 w-4 animate-spin" /> Loading…
      </div>
      <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
      <p v-else-if="!items.length" class="text-sm text-muted-foreground py-6">
        No {{ kind === 'video' ? 'videos' : 'music or voice generations' }} yet.
      </p>
      <div v-else class="grid gap-3" :class="kind === 'video' ? 'grid-cols-2 md:grid-cols-3' : 'grid-cols-1'">
        <div v-for="it in items" :key="it.ref" class="rounded-md border p-2 space-y-2">
          <video v-if="kind === 'video'" :src="it.url" class="w-full rounded" muted preload="metadata" controls />
          <audio v-else :src="it.url" class="w-full" preload="none" controls />
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-muted-foreground line-clamp-2">
              <span class="font-medium">{{ it.type }}</span> · {{ it.label }}
            </span>
            <Button size="sm" variant="secondary" @click="pick(it)">Use</Button>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
