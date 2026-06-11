<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowLeft, Trash2, Settings2, X, Play, Pause, Shuffle, Clapperboard,
  Music, Palette, GripVertical, ArrowUp, ArrowDown, ListMusic, LayoutList,
} from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import type { Collection, InferenceRequest, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'
import { usePlayerStore } from '@/stores/player'
import { tracksFromRequests, formatTrackTime, formatRuntime } from '@/utils/player'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const route = useRoute()
const slug = computed(() => String(route.params.slug))
const {
  getCollection, updateCollection, deleteCollection, removeFromCollection,
  reorderCollection,
} = useContentSharing()
const player = usePlayerStore()

const collection = ref<Collection | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const editOpen = ref(false)
const coverOpen = ref(false)
const form = ref<{ name: string; description: string; visibility: Visibility }>({
  name: '', description: '', visibility: 'UNLISTED',
})
const saving = ref(false)

const items = computed<InferenceRequest[]>(() => collection.value?.items ?? [])
const tracks = computed(() => tracksFromRequests(items.value))
const videoItems = computed(() => items.value.filter((r) => r.video_url))
const runtime = computed(() =>
  formatRuntime(
    collection.value?.total_audio_seconds ??
      tracks.value.reduce((s, tr) => s + (tr.duration ?? 0), 0),
  ),
)

// Playlist (track rows) vs Manage (full cards, remove + reorder). Music-heavy
// collections open in playlist mode; everything else opens in manage mode.
const view = ref<'playlist' | 'manage'>('manage')
onMounted(async () => {
  await load()
  if (tracks.value.length > 0) view.value = 'playlist'
})

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collection.value = await getCollection(slug.value)
  } catch {
    error.value = t('media.collectionNotFound')
  } finally {
    loading.value = false
  }
}

// --- playback ---------------------------------------------------------------

const trackQueueIndex = (id: string) => tracks.value.findIndex((tr) => tr.id === id)

const playAll = () => player.playQueue(tracks.value, 0)
const shuffleAll = () => player.playQueue(tracks.value, -1, { shuffle: true })
const playFrom = (id: string) => {
  const i = trackQueueIndex(id)
  if (i >= 0) player.playQueue(tracks.value, i)
}
const isCurrent = (id: string) => player.current?.id === id

const watchVideos = () => {
  const first = videoItems.value[0]
  if (first) navigateTo(`/dashboard/watch/${first.id}?list=${slug.value}`)
}

// --- editing ------------------------------------------------------------------

const openEdit = () => {
  if (!collection.value) return
  form.value = {
    name: collection.value.name,
    description: collection.value.description || '',
    visibility: collection.value.visibility,
  }
  editOpen.value = true
}

const save = async () => {
  if (!collection.value) return
  saving.value = true
  try {
    const updated = await updateCollection(slug.value, {
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      visibility: form.value.visibility,
    })
    collection.value = { ...collection.value, ...updated, items: collection.value.items }
    editOpen.value = false
    toast.success('Collection updated')
  } catch {
    toast.error('Failed to update collection')
  } finally {
    saving.value = false
  }
}

const remove = async () => {
  try {
    await deleteCollection(slug.value)
    toast.success('Collection deleted')
    navigateTo('/dashboard/inference/collections')
  } catch {
    toast.error('Failed to delete collection')
  }
}

const removeItem = async (id: string) => {
  if (!collection.value) return
  try {
    await removeFromCollection(slug.value, id)
    collection.value.items = (collection.value.items || []).filter(
      (r) => String(r.id) !== String(id),
    )
    collection.value.item_count = Math.max(0, collection.value.item_count - 1)
    toast.success('Removed from collection')
  } catch {
    toast.error('Failed to remove item')
  }
}

const onCoverUpdated = (url: string | null) => {
  if (collection.value) collection.value.cover_image_url = url
}

// --- reordering (owner, manage view) ------------------------------------------

const reordering = ref(false)
const persistOrder = async () => {
  if (!collection.value) return
  reordering.value = true
  try {
    await reorderCollection(
      slug.value,
      items.value.map((r) => r.id),
    )
  } catch {
    toast.error('Failed to save the new order')
    await load() // resync with the server's order
  } finally {
    reordering.value = false
  }
}

const moveItem = async (index: number, delta: number) => {
  const list = collection.value?.items
  if (!list) return
  const target = index + delta
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target], list[index]]
  await persistOrder()
}

const dragIndex = ref<number | null>(null)
const onDragStart = (i: number) => {
  dragIndex.value = i
}
const onDrop = async (i: number) => {
  const list = collection.value?.items
  const from = dragIndex.value
  dragIndex.value = null
  if (!list || from === null || from === i) return
  const [moved] = list.splice(from, 1)
  list.splice(i, 0, moved)
  await persistOrder()
}
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <NuxtLink
      to="/dashboard/inference/collections"
      class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
    >
      <ArrowLeft class="size-4" /> All collections
    </NuxtLink>

    <div v-if="loading && !collection" class="space-y-4">
      <div class="h-8 w-64 bg-muted rounded animate-pulse" />
      <Card class="p-4 animate-pulse h-40" />
    </div>

    <div v-else-if="error" class="text-destructive text-center py-12">{{ error }}</div>

    <template v-else-if="collection">
      <!-- Playlist-style header: square cover + meta + transport -->
      <div class="mb-6 flex flex-col gap-5 sm:flex-row sm:items-end">
        <div class="relative size-36 shrink-0 sm:size-44">
          <img
            v-if="collection.cover_image_url"
            :src="collection.cover_image_url"
            class="size-full rounded-xl border object-cover shadow-sm"
            :alt="collection.name"
          />
          <div v-else class="flex size-full items-center justify-center rounded-xl border bg-muted">
            <Music class="size-10 text-muted-foreground" />
          </div>
          <Button
            v-if="collection.is_owner"
            variant="secondary"
            size="icon"
            class="absolute bottom-2 right-2 size-8 shadow"
            :title="t('media.generateCover')"
            data-testid="collection-cover-button"
            @click="coverOpen = true"
          >
            <Palette class="size-4" />
          </Button>
        </div>

        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-2xl font-bold break-words">{{ collection.name }}</h1>
            <VisibilityBadge :visibility="collection.visibility" />
          </div>
          <p v-if="collection.description" class="text-muted-foreground mt-1 break-words">
            {{ collection.description }}
          </p>
          <p class="text-sm text-muted-foreground mt-1">
            {{ collection.item_count }} item{{ collection.item_count === 1 ? '' : 's' }}
            <template v-if="tracks.length">
              · {{ tracks.length }} {{ t('media.songs', tracks.length) }}<template v-if="runtime"> · {{ runtime }}</template>
            </template>
            <template v-if="videoItems.length">
              · {{ videoItems.length }} {{ t('media.videos', videoItems.length) }}
            </template>
          </p>

          <div class="mt-3 flex items-center gap-2 flex-wrap">
            <Button
              v-if="tracks.length"
              class="gap-2 rounded-full"
              data-testid="collection-play"
              @click="playAll"
            >
              <Play class="size-4" /> {{ t('media.play') }}
            </Button>
            <Button
              v-if="tracks.length > 1"
              variant="outline"
              class="gap-2 rounded-full"
              data-testid="collection-shuffle"
              @click="shuffleAll"
            >
              <Shuffle class="size-4" /> {{ t('media.shuffle') }}
            </Button>
            <Button
              v-if="videoItems.length"
              variant="outline"
              class="gap-2 rounded-full"
              data-testid="collection-watch"
              @click="watchVideos"
            >
              <Clapperboard class="size-4" /> {{ t('media.playVideos') }}
            </Button>

            <div class="ml-auto flex items-center gap-2">
              <Button v-if="collection.is_owner" variant="outline" size="sm" @click="openEdit">
                <Settings2 class="size-4" /> Edit
              </Button>
              <AlertDialog v-if="collection.is_owner">
                <AlertDialogTrigger as-child>
                  <Button variant="outline" size="sm" class="text-destructive hover:text-destructive">
                    <Trash2 class="size-4" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this collection?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This deletes the “{{ collection.name }}” collection. The requests
                      inside are not deleted.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      class="bg-destructive text-white hover:bg-destructive/90"
                      @click="remove"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </div>
      </div>

      <!-- View toggle (playlist mode only exists when there's music) -->
      <div v-if="tracks.length" class="mb-4 flex items-center gap-1">
        <Button
          :variant="view === 'playlist' ? 'secondary' : 'ghost'"
          size="sm"
          class="gap-1.5"
          @click="view = 'playlist'"
        >
          <ListMusic class="size-4" /> {{ t('media.playlistView') }}
        </Button>
        <Button
          :variant="view === 'manage' ? 'secondary' : 'ghost'"
          size="sm"
          class="gap-1.5"
          data-testid="collection-manage-view"
          @click="view = 'manage'"
        >
          <LayoutList class="size-4" /> {{ t('media.manageView') }}
        </Button>
      </div>

      <div
        v-if="!items.length"
        class="text-center py-12 text-muted-foreground"
      >
        This collection is empty — add requests from any request's “⋯ → Add to collection”.
      </div>

      <!-- Playlist view: compact Spotify-style track rows -->
      <div v-else-if="view === 'playlist' && tracks.length" class="rounded-xl border">
        <div
          v-for="(tr, i) in tracks"
          :key="tr.id"
          class="group flex cursor-pointer items-center gap-3 border-b px-3 py-2.5 last:border-b-0 hover:bg-accent/50"
          :class="isCurrent(tr.id) ? 'bg-accent/40' : ''"
          :data-testid="`track-row-${i}`"
          @click="playFrom(tr.id)"
        >
          <div class="flex w-8 shrink-0 items-center justify-center">
            <span
              class="text-sm tabular-nums text-muted-foreground group-hover:hidden"
              :class="isCurrent(tr.id) ? 'text-primary' : ''"
            >{{ i + 1 }}</span>
            <component
              :is="isCurrent(tr.id) && player.playing ? Pause : Play"
              class="hidden size-4 group-hover:block"
            />
          </div>
          <img
            v-if="tr.coverUrl"
            :src="tr.coverUrl"
            class="size-10 shrink-0 rounded-md border object-cover"
            :alt="tr.title"
            loading="lazy"
          />
          <div v-else class="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Music class="size-4 text-muted-foreground" />
          </div>
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm" :class="isCurrent(tr.id) ? 'text-primary font-medium' : ''" :title="tr.title">
              {{ tr.title }}
            </p>
            <p v-if="tr.owner" class="truncate text-xs text-muted-foreground">{{ tr.owner }}</p>
          </div>
          <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
            {{ formatTrackTime(tr.duration) }}
          </span>
        </div>
      </div>

      <!-- Manage view: full cards with remove + reorder -->
      <div v-else class="space-y-4">
        <div
          v-for="(request, i) in items"
          :key="request.id"
          class="relative"
          :class="dragIndex === i ? 'opacity-60' : ''"
          :draggable="collection.is_owner ? true : undefined"
          @dragstart="onDragStart(i)"
          @dragover.prevent
          @drop="onDrop(i)"
          @dragend="dragIndex = null"
        >
          <div class="flex items-start gap-2">
            <div
              v-if="collection.is_owner"
              class="flex shrink-0 flex-col items-center gap-1 pt-3 text-muted-foreground"
            >
              <button
                class="cursor-grab rounded p-0.5 hover:text-foreground active:cursor-grabbing"
                :title="t('media.dragToReorder')"
              >
                <GripVertical class="size-4" />
              </button>
              <button
                class="rounded p-0.5 hover:text-foreground disabled:opacity-30"
                :disabled="i === 0 || reordering"
                :title="t('media.moveUp')"
                :data-testid="`move-up-${i}`"
                @click="moveItem(i, -1)"
              >
                <ArrowUp class="size-4" />
              </button>
              <button
                class="rounded p-0.5 hover:text-foreground disabled:opacity-30"
                :disabled="i === items.length - 1 || reordering"
                :title="t('media.moveDown')"
                :data-testid="`move-down-${i}`"
                @click="moveItem(i, 1)"
              >
                <ArrowDown class="size-4" />
              </button>
            </div>
            <div class="min-w-0 flex-1">
              <InferenceRequestCard :request="request" />
            </div>
          </div>
          <Button
            v-if="collection.is_owner"
            variant="outline"
            size="icon"
            class="absolute -top-2 -right-2 size-7 rounded-full bg-background shadow-sm"
            title="Remove from collection"
            @click="removeItem(String(request.id))"
          >
            <X class="size-4" />
          </Button>
        </div>
      </div>
    </template>

    <!-- Edit dialog -->
    <Dialog v-model:open="editOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit collection</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-1.5">
            <Label>Name</Label>
            <Input v-model="form.name" />
          </div>
          <div class="space-y-1.5">
            <Label>Description</Label>
            <Textarea v-model="form.description" rows="2" />
          </div>
          <div class="space-y-1.5">
            <Label>Visibility</Label>
            <Select v-model="form.visibility">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="v in VISIBILITY_ORDER" :key="v" :value="v">
                  {{ VISIBILITY_META[v].label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="editOpen = false">Cancel</Button>
          <Button :disabled="saving || !form.name.trim()" @click="save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <GenerateCoverDialog
      v-if="collection?.is_owner"
      v-model:open="coverOpen"
      :target="{ kind: 'collection', slug }"
      :seed-prompt="`${collection.name}. ${collection.description || ''}`"
      @updated="onCoverUpdated"
    />
  </div>
</template>
