<script setup lang="ts">
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Star, Bookmark, Share2, MoreHorizontal, Eye, FolderPlus,
} from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = withDefaults(
  defineProps<{ request: InferenceRequest; showShare?: boolean }>(),
  { showShare: true },
)
const emit = defineEmits<{ (e: 'visibility-change', v: Visibility): void }>()

const { toggleStar, toggleBookmark, shareUrl } = useContentSharing()

// Local, optimistic state seeded from the request (resynced when the row swaps).
const starred = ref(!!props.request.is_starred)
const starCount = ref(props.request.star_count ?? 0)
const bookmarked = ref(!!props.request.is_bookmarked)
const visEditOpen = ref(false)
const collectOpen = ref(false)
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
  // optimistic
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

const onShare = async () => {
  const link = shareUrl(props.request.share_token)
  if (!link) return
  try {
    await navigator.clipboard.writeText(link)
    toast.success('Share link copied')
  } catch {
    toast.error('Could not copy link')
  }
}

const onVisibilityUpdated = (v: Visibility) => {
  // Let the parent reflect the change (the request object it owns drives the
  // visibility badge); we avoid mutating the prop directly here.
  emit('visibility-change', v)
}
</script>

<template>
  <div class="flex items-center gap-1" @click.stop>
    <!-- Star -->
    <Button
      variant="ghost"
      size="sm"
      class="h-8 px-2 gap-1"
      :class="starred ? 'text-amber-500' : 'text-muted-foreground'"
      :title="starred ? 'Unstar' : 'Star'"
      @click="onStar"
    >
      <Star class="size-4" :class="starred ? 'fill-current' : ''" />
      <span v-if="starCount > 0" class="text-xs tabular-nums">{{ starCount }}</span>
    </Button>

    <!-- Bookmark -->
    <Button
      variant="ghost"
      size="icon"
      class="size-8"
      :class="bookmarked ? 'text-primary' : 'text-muted-foreground'"
      :title="bookmarked ? 'Remove bookmark' : 'Bookmark to your profile'"
      @click="onBookmark"
    >
      <Bookmark class="size-4" :class="bookmarked ? 'fill-current' : ''" />
    </Button>

    <!-- Share (owner only — others use the page URL) -->
    <Button
      v-if="showShare && request.is_owner && request.share_token"
      variant="ghost"
      size="icon"
      class="size-8 text-muted-foreground"
      title="Copy share link"
      @click="onShare"
    >
      <Share2 class="size-4" />
    </Button>

    <!-- Owner menu: visibility + collections -->
    <DropdownMenu v-if="request.is_owner">
      <DropdownMenuTrigger as-child>
        <Button variant="ghost" size="icon" class="size-8 text-muted-foreground" title="More">
          <MoreHorizontal class="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem @select="visEditOpen = true">
          <Eye class="size-4" /> Edit visibility
        </DropdownMenuItem>
        <DropdownMenuItem @select="collectOpen = true">
          <FolderPlus class="size-4" /> Add to collection
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>

    <EditVisibilityDialog
      v-if="request.is_owner"
      v-model:open="visEditOpen"
      :request="request"
      @updated="onVisibilityUpdated"
    />
    <AddToCollectionDialog
      v-if="request.is_owner"
      v-model:open="collectOpen"
      :request="request"
    />
  </div>
</template>
