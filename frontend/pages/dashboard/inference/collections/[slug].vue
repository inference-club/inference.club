<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ArrowLeft, Trash2, Settings2, X } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import type { Collection, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

definePageMeta({ layout: 'app' })

const route = useRoute()
const slug = computed(() => String(route.params.slug))
const {
  getCollection, updateCollection, deleteCollection, removeFromCollection,
} = useContentSharing()

const collection = ref<Collection | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const editOpen = ref(false)
const form = ref<{ name: string; description: string; visibility: Visibility }>({
  name: '', description: '', visibility: 'UNLISTED',
})
const saving = ref(false)

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collection.value = await getCollection(slug.value)
  } catch {
    error.value = 'Collection not found'
  } finally {
    loading.value = false
  }
}

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
    collection.value = { ...collection.value, ...updated }
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

onMounted(load)
</script>

<template>
  <div class="container mx-auto py-6 max-w-5xl">
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
      <div class="flex items-start justify-between gap-4 mb-6">
        <div class="min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-2xl font-bold">{{ collection.name }}</h1>
            <VisibilityBadge :visibility="collection.visibility" />
          </div>
          <p v-if="collection.description" class="text-muted-foreground mt-1">
            {{ collection.description }}
          </p>
          <p class="text-sm text-muted-foreground mt-1">
            {{ collection.item_count }} item{{ collection.item_count === 1 ? '' : 's' }}
          </p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" @click="openEdit">
            <Settings2 class="size-4" /> Edit
          </Button>
          <AlertDialog>
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

      <div
        v-if="!collection.items?.length"
        class="text-center py-12 text-muted-foreground"
      >
        This collection is empty — add requests from any request's “⋯ → Add to collection”.
      </div>

      <div v-else class="space-y-4">
        <div v-for="request in collection.items" :key="request.id" class="relative">
          <InferenceRequestCard :request="request" />
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
  </div>
</template>
