<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  FileText, Film, Image as ImageIcon, Loader2, Lock, Globe, Music, Trash2,
} from 'lucide-vue-next'
import { useUploads, type MediaFile } from '@/composables/useUploads'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'

definePageMeta({ layout: 'app', requireAuth: true })

const { listFiles, updateFile, deleteFile } = useUploads()

const PAGE = 48
const items = ref<MediaFile[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

// Filters
type KindFilter = { label: string; value: string }
const kindFilters: KindFilter[] = [
  { label: 'All', value: '' },
  { label: 'Images', value: 'INPUT_IMAGE' },
  { label: 'Audio', value: 'INPUT_AUDIO' },
  { label: 'Video', value: 'INPUT_VIDEO' },
  { label: 'Documents', value: 'INPUT_DOC' },
]
const kind = ref('')
const source = ref<'' | 'true' | 'false'>('') // '' all, 'false' uploads, 'true' used

const selected = ref<MediaFile | null>(null)
const sheetOpen = ref(false)

const isImage = (k: string) => k.endsWith('IMAGE')
const isAudio = (k: string) => k.endsWith('AUDIO')
const isVideo = (k: string) => k.endsWith('VIDEO')

const iconFor = (k: string) =>
  isImage(k) ? ImageIcon : isAudio(k) ? Music : isVideo(k) ? Film : FileText

const isPublic = (v: string) => v === 'PUBLIC' || v === 'UNLISTED'

const prettySize = (n: number | null) => {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
const prettyKind = (k: string) =>
  k.replace(/^INPUT_|^OUTPUT_/, '').toLowerCase()

const load = async (reset = true) => {
  loading.value = true
  error.value = null
  try {
    if (reset) {
      offset.value = 0
      items.value = []
    }
    const res = await listFiles({
      kind: kind.value || undefined,
      bound: source.value || undefined,
      limit: PAGE,
      offset: offset.value,
    })
    items.value = reset ? res.data : [...items.value, ...res.data]
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load media'
  } finally {
    loading.value = false
  }
}

const setKind = (v: string) => {
  if (kind.value === v) return
  kind.value = v
  load()
}
const setSource = (v: '' | 'true' | 'false') => {
  if (source.value === v) return
  source.value = v
  load()
}
const loadMore = () => {
  offset.value += PAGE
  load(false)
}

const open = (item: MediaFile) => {
  selected.value = item
  sheetOpen.value = true
}

const toggleVisibility = async () => {
  const item = selected.value
  if (!item) return
  const next = isPublic(item.visibility) ? 'SECRET' : 'PUBLIC'
  try {
    const updated = await updateFile(item.public_id, { visibility: next })
    item.visibility = updated.visibility
    const idx = items.value.findIndex((i) => i.public_id === item.public_id)
    if (idx >= 0) items.value[idx].visibility = updated.visibility
    toast.success(isPublic(updated.visibility) ? 'Made public' : 'Made private')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Could not update visibility')
  }
}

const remove = async () => {
  const item = selected.value
  if (!item) return
  if (!confirm('Delete this media permanently? This cannot be undone.')) return
  try {
    await deleteFile(item.public_id)
    items.value = items.value.filter((i) => i.public_id !== item.public_id)
    total.value = Math.max(0, total.value - 1)
    sheetOpen.value = false
    toast.success('Deleted')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Could not delete')
  }
}

const canLoadMore = computed(() => items.value.length < total.value)

onMounted(() => load())
</script>

<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-4 flex items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold">Media library</h1>
        <p class="text-sm text-muted-foreground">
          Everything you've uploaded or generated — private to you unless you publish it.
        </p>
      </div>
      <span class="shrink-0 text-sm text-muted-foreground">{{ total }} item{{ total === 1 ? '' : 's' }}</span>
    </div>

    <!-- Filters -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <Button
        v-for="f in kindFilters"
        :key="f.value"
        size="sm"
        :variant="kind === f.value ? 'default' : 'outline'"
        @click="setKind(f.value)"
      >
        {{ f.label }}
      </Button>
      <span class="mx-1 h-5 w-px bg-border" />
      <Button size="sm" :variant="source === '' ? 'secondary' : 'ghost'" @click="setSource('')">All</Button>
      <Button size="sm" :variant="source === 'false' ? 'secondary' : 'ghost'" @click="setSource('false')">Uploads</Button>
      <Button size="sm" :variant="source === 'true' ? 'secondary' : 'ghost'" @click="setSource('true')">Used in a request</Button>
    </div>

    <div v-if="error" class="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
      {{ error }}
    </div>

    <!-- Empty -->
    <div
      v-else-if="!loading && !items.length"
      class="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground"
    >
      No media yet. Attach a file in any playground, or upload one — it'll show up here.
    </div>

    <!-- Grid -->
    <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
      <button
        v-for="item in items"
        :key="item.public_id"
        type="button"
        class="group relative aspect-square overflow-hidden rounded-lg border bg-muted/40 text-left transition hover:ring-2 hover:ring-ring"
        @click="open(item)"
      >
        <img
          v-if="isImage(item.kind)"
          :src="item.url"
          :alt="prettyKind(item.kind)"
          class="size-full object-cover"
          loading="lazy"
        />
        <div v-else class="flex size-full flex-col items-center justify-center gap-2 p-2 text-center">
          <component :is="iconFor(item.kind)" class="size-7 text-muted-foreground" />
          <span class="text-[10px] uppercase tracking-wide text-muted-foreground">{{ prettyKind(item.kind) }}</span>
        </div>
        <!-- visibility corner -->
        <span class="absolute right-1 top-1 rounded-full bg-background/80 p-1">
          <Globe v-if="isPublic(item.visibility)" class="size-3 text-emerald-600" />
          <Lock v-else class="size-3 text-muted-foreground" />
        </span>
      </button>
    </div>

    <div class="mt-5 flex justify-center">
      <Button v-if="canLoadMore" variant="outline" :disabled="loading" @click="loadMore">
        <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
        Load more
      </Button>
      <Loader2 v-else-if="loading" class="size-5 animate-spin text-muted-foreground" />
    </div>

    <!-- Detail sheet -->
    <Sheet v-model:open="sheetOpen">
      <SheetContent class="w-full overflow-y-auto sm:max-w-md">
        <template v-if="selected">
          <SheetHeader>
            <SheetTitle class="capitalize">{{ prettyKind(selected.kind) }}</SheetTitle>
          </SheetHeader>

          <div class="mt-4 space-y-4">
            <div class="overflow-hidden rounded-lg border bg-muted/40">
              <img v-if="isImage(selected.kind)" :src="selected.url" :alt="prettyKind(selected.kind)" class="max-h-80 w-full object-contain" />
              <video v-else-if="isVideo(selected.kind)" :src="selected.url" controls class="max-h-80 w-full" />
              <audio v-else-if="isAudio(selected.kind)" :src="selected.url" controls class="w-full p-3" />
              <a v-else :href="selected.url" target="_blank" class="block p-6 text-center text-sm text-primary underline">Open document</a>
            </div>

            <dl class="space-y-1.5 text-sm">
              <div class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Visibility</dt>
                <dd>
                  <Badge :variant="isPublic(selected.visibility) ? 'default' : 'secondary'">
                    {{ selected.visibility }}
                  </Badge>
                </dd>
              </div>
              <div v-if="selected.size_bytes" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Size</dt>
                <dd>{{ prettySize(selected.size_bytes) }}</dd>
              </div>
              <div v-if="selected.content_type" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Type</dt>
                <dd class="truncate">{{ selected.content_type }}</dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Added</dt>
                <dd>{{ new Date(selected.created_on).toLocaleDateString() }}</dd>
              </div>
              <div v-if="selected.produced_by" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Used in</dt>
                <dd class="capitalize">a {{ selected.produced_by.type.toLowerCase() }} request</dd>
              </div>
              <div v-if="selected.derivatives?.length" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Derived outputs</dt>
                <dd>{{ selected.derivatives.length }}</dd>
              </div>
            </dl>

            <div class="flex items-center gap-2 pt-2">
              <Button variant="outline" class="flex-1" @click="toggleVisibility">
                <component :is="isPublic(selected.visibility) ? Lock : Globe" class="mr-2 size-4" />
                {{ isPublic(selected.visibility) ? 'Make private' : 'Make public' }}
              </Button>
              <Button variant="ghost" size="icon" class="text-destructive hover:text-destructive" @click="remove">
                <Trash2 class="size-4" />
              </Button>
            </div>
          </div>
        </template>
      </SheetContent>
    </Sheet>
  </div>
</template>
