<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { FolderPlus, Library } from 'lucide-vue-next'
import type { Collection, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'
import CollectionCard from '@/components/CollectionCard.vue'

definePageMeta({ layout: 'app' })

const { listCollections, createCollection } = useContentSharing()

const collections = ref<Collection[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const createOpen = ref(false)
const form = ref<{ name: string; description: string; visibility: Visibility }>({
  name: '',
  description: '',
  visibility: 'UNLISTED',
})
const creating = ref(false)

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collections.value = await listCollections()
  } catch {
    error.value = 'Failed to load collections'
  } finally {
    loading.value = false
  }
}

const create = async () => {
  if (!form.value.name.trim()) return
  creating.value = true
  try {
    const col = await createCollection({
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      visibility: form.value.visibility,
    })
    collections.value.unshift(col)
    createOpen.value = false
    form.value = { name: '', description: '', visibility: 'UNLISTED' }
    toast.success('Collection created')
    navigateTo(`/dashboard/inference/collections/${col.slug}`)
  } catch {
    toast.error('Failed to create collection')
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="container mx-auto py-6">
    <div class="flex flex-wrap items-end justify-between gap-y-2 mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Library class="size-6" /> Collections
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Group your inference requests to organize and share them.
        </p>
      </div>
      <Button @click="createOpen = true">
        <FolderPlus class="size-4" /> New collection
      </Button>
    </div>

    <div v-if="error" class="text-destructive text-center py-8">{{ error }}</div>

    <div
      v-else-if="!loading && collections.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      No collections yet — create one to group related requests.
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <CollectionCard
        v-for="col in collections"
        :key="col.slug"
        :collection="col"
        :to="`/dashboard/inference/collections/${col.slug}`"
      />
    </div>

    <!-- Create dialog -->
    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New collection</DialogTitle>
          <DialogDescription>Name it and choose who can see it.</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-1.5">
            <Label>Name</Label>
            <Input v-model="form.name" placeholder="e.g. Best landscapes" @keyup.enter="create" />
          </div>
          <div class="space-y-1.5">
            <Label>Description <span class="text-muted-foreground">(optional)</span></Label>
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
          <Button variant="ghost" @click="createOpen = false">Cancel</Button>
          <Button :disabled="creating || !form.name.trim()" @click="create">Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
