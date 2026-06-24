<script setup lang="ts">
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Plus, FolderPlus, Loader2, Check } from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{ open: boolean; request: InferenceRequest }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const { listCollections, createCollection, addToCollection } = useContentSharing()

const collections = ref<Collection[]>([])
const loading = ref(false)
const busySlug = ref<string | null>(null)
// Collections this song was added to during this dialog session — drives the
// "Added ✓" affordance so a successful add is visibly confirmed (the add
// itself is idempotent server-side).
const addedSlugs = ref<Set<string>>(new Set())
const newName = ref('')
const creating = ref(false)

const load = async () => {
  loading.value = true
  try {
    collections.value = await listCollections()
  } catch {
    toast.error('Failed to load collections')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (o) => {
    if (o) {
      addedSlugs.value = new Set()
      load()
    }
  },
)

const add = async (col: Collection) => {
  if (busySlug.value) return
  busySlug.value = col.slug
  try {
    await addToCollection(col.slug, props.request.id)
    // Reflect the add immediately: mark it and bump the count (once per
    // session, so re-clicking an already-added row doesn't over-count).
    if (!addedSlugs.value.has(col.slug)) {
      col.item_count = (col.item_count ?? 0) + 1
      addedSlugs.value = new Set(addedSlugs.value).add(col.slug)
    }
    toast.success(`Added to “${col.name}”`)
  } catch {
    toast.error('Failed to add to collection')
  } finally {
    busySlug.value = null
  }
}

const create = async () => {
  const name = newName.value.trim()
  if (!name) return
  creating.value = true
  try {
    const col = await createCollection({ name })
    collections.value.unshift(col)
    newName.value = ''
    await add(col)
  } catch {
    toast.error('Failed to create collection')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Add to collection</DialogTitle>
        <DialogDescription>
          Organize request #{{ request.id }} into one or more collections.
        </DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="py-6 text-center text-sm text-muted-foreground">
        Loading…
      </div>

      <div v-else class="space-y-2 max-h-64 overflow-y-auto">
        <p v-if="!collections.length" class="text-sm text-muted-foreground py-2">
          No collections yet — create one below.
        </p>
        <button
          v-for="col in collections"
          :key="col.slug"
          type="button"
          class="w-full flex items-center justify-between gap-3 rounded-lg border p-3 text-left transition-colors"
          :class="addedSlugs.has(col.slug) ? 'border-green-500/40 bg-green-500/5' : 'hover:bg-muted/50'"
          :disabled="busySlug === col.slug"
          @click="add(col)"
        >
          <div class="min-w-0">
            <div class="font-medium text-sm truncate">{{ col.name }}</div>
            <div class="text-xs text-muted-foreground">{{ col.item_count }} item{{ col.item_count === 1 ? '' : 's' }}</div>
          </div>
          <Loader2 v-if="busySlug === col.slug" class="size-4 animate-spin shrink-0" />
          <span v-else-if="addedSlugs.has(col.slug)" class="flex shrink-0 items-center gap-1 text-xs font-medium text-green-600">
            <Check class="size-4" /> Added
          </span>
          <Plus v-else class="size-4 shrink-0 text-muted-foreground" />
        </button>
      </div>

      <div class="flex items-center gap-2 pt-2 border-t">
        <Input v-model="newName" placeholder="New collection name" @keyup.enter="create" />
        <Button variant="outline" :disabled="creating || !newName.trim()" @click="create">
          <FolderPlus class="size-4" />
          Create
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
