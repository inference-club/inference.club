<script setup lang="ts">
// Compact star + bookmark pair for dense list rows and grid cards (track
// lists, video cards) where the full RequestActionBar would crowd the layout.
// Same endpoints and optimistic behavior as the action bar.

import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Star, Bookmark } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{ request: InferenceRequest }>()

const { toggleStar, toggleBookmark } = useContentSharing()

// Local, optimistic state seeded from the request (resynced when the row swaps).
const starred = ref(!!props.request.is_starred)
const starCount = ref(props.request.star_count ?? 0)
const bookmarked = ref(!!props.request.is_bookmarked)
const busy = ref(false)

watch(
  () => props.request.id,
  () => {
    starred.value = !!props.request.is_starred
    starCount.value = props.request.star_count ?? 0
    bookmarked.value = !!props.request.is_bookmarked
  },
)

const onStar = async () => {
  if (busy.value) return
  busy.value = true
  const next = !starred.value
  starred.value = next
  starCount.value += next ? 1 : -1
  try {
    const res = await toggleStar(props.request.id, next)
    starred.value = res.is_starred
    starCount.value = res.star_count
  } catch {
    starred.value = !next
    starCount.value += next ? -1 : 1
    toast.error('Sign in to star requests')
  } finally {
    busy.value = false
  }
}

const onBookmark = async () => {
  if (busy.value) return
  busy.value = true
  const next = !bookmarked.value
  bookmarked.value = next
  try {
    const res = await toggleBookmark(props.request.id, next)
    bookmarked.value = res.is_bookmarked
    toast.success(next ? 'Bookmarked to your profile' : 'Removed bookmark')
  } catch {
    bookmarked.value = !next
    toast.error('Sign in to bookmark requests')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex shrink-0 items-center" @click.stop>
    <Button
      variant="ghost"
      size="sm"
      class="h-7 gap-1 px-1.5"
      :class="starred ? 'text-amber-500' : 'text-muted-foreground'"
      :title="starred ? 'Unstar' : 'Star'"
      data-testid="quick-star"
      @click="onStar"
    >
      <Star class="size-3.5" :class="starred ? 'fill-current' : ''" />
      <span v-if="starCount > 0" class="text-xs tabular-nums">{{ starCount }}</span>
    </Button>
    <Button
      variant="ghost"
      size="icon"
      class="size-7"
      :class="bookmarked ? 'text-primary' : 'text-muted-foreground'"
      :title="bookmarked ? 'Remove bookmark' : 'Bookmark to your profile'"
      data-testid="quick-bookmark"
      @click="onBookmark"
    >
      <Bookmark class="size-3.5" :class="bookmarked ? 'fill-current' : ''" />
    </Button>
  </div>
</template>
