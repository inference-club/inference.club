<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Star, Bookmark, MoreHorizontal, Eye, FolderPlus, Flag, RotateCcw, Loader2, Palette, Megaphone,
  Share2, Link as LinkIcon, Trash2,
} from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useAuth } from '@/composables/useAuth'
import { isRetryable } from '@/utils/inference'

const props = withDefaults(
  defineProps<{
    request: InferenceRequest
    showShare?: boolean
    // Dense mode (used by the cramped card header): fold Share, Feature and
    // Delete into the ⋯ menu so only Star + Bookmark + ⋯ stay inline.
    dense?: boolean
    // Offer a Delete entry in the ⋯ menu (owner only). The host handles it.
    canDelete?: boolean
    deleting?: boolean
  }>(),
  { showShare: true },
)
const emit = defineEmits<{
  (e: 'visibility-change', v: Visibility): void
  (e: 'retried' | 'delete'): void
}>()

const { toggleStar, toggleBookmark, toggleFeatured, shareUrl } = useContentSharing()

// Share affordance is owner-only (only the owner holds the share_token) and
// pointless for SECRET requests (the link wouldn't resolve for anyone else).
const shareable = computed(
  () =>
    props.showShare &&
    props.request.is_owner &&
    !!props.request.share_token &&
    props.request.visibility !== 'SECRET',
)
const shareLink = computed(() => shareUrl(props.request.share_token))
const shareText = computed(() => {
  const m = props.request.model_name
  return m ? `Inference with ${m} on inference.club` : 'Check out this inference on inference.club'
})
const copyShareLink = async () => {
  if (!shareLink.value) return
  try {
    await navigator.clipboard.writeText(shareLink.value)
    toast.success('Share link copied')
  } catch {
    toast.error('Could not copy link')
  }
}
const openIntent = (url: string) => window.open(url, '_blank', 'noopener,noreferrer')
const shareToX = () => {
  if (!shareLink.value) return
  openIntent(
    `https://x.com/intent/tweet?url=${encodeURIComponent(shareLink.value)}` +
      `&text=${encodeURIComponent(shareText.value)}`,
  )
}
const shareToReddit = () => {
  if (!shareLink.value) return
  openIntent(
    `https://www.reddit.com/submit?url=${encodeURIComponent(shareLink.value)}` +
      `&title=${encodeURIComponent(shareText.value)}`,
  )
}

const deleteOpen = ref(false)
const { retryInferenceRequest } = useInferenceRequest()
const { isAuthenticated, user } = useAuth()

const retryable = computed(() => isRetryable(props.request))
const retrying = ref(false)

const onRetry = async () => {
  if (retrying.value) return
  retrying.value = true
  try {
    await retryInferenceRequest(props.request.id)
    toast.success('Retried — generating again')
    emit('retried')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Retry failed')
  } finally {
    retrying.value = false
  }
}

// Local, optimistic state seeded from the request (resynced when the row swaps).
const starred = ref(!!props.request.is_starred)
const starCount = ref(props.request.star_count ?? 0)
const bookmarked = ref(!!props.request.is_bookmarked)
const featured = ref(!!props.request.is_featured)

// Staff-only home-page curation: only PUBLIC requests qualify (the backend
// rejects everything else, so hide the affordance rather than offer a 400).
const canFeature = computed(
  () => !!user.value?.is_staff && props.request.visibility === 'PUBLIC',
)
const visEditOpen = ref(false)
const collectOpen = ref(false)
const reportOpen = ref(false)
const coverOpen = ref(false)
const busy = ref(false)

// Cover art applies to tracks (MUSIC) — seeded from the song's prompt.
const isTrack = computed(() => props.request.inference_type === 'MUSIC')
const coverSeed = computed(() => {
  const payloadPrompt =
    typeof props.request.payload?.prompt === 'string'
      ? (props.request.payload.prompt as string)
      : ''
  return props.request.prompt_preview || payloadPrompt || ''
})

watch(
  () => props.request.id,
  () => {
    starred.value = !!props.request.is_starred
    starCount.value = props.request.star_count ?? 0
    bookmarked.value = !!props.request.is_bookmarked
    featured.value = !!props.request.is_featured
  },
)

const onFeature = async () => {
  if (busy.value) return
  busy.value = true
  const next = !featured.value
  featured.value = next
  try {
    const res = await toggleFeatured(props.request.id, next)
    featured.value = res.is_featured
    toast.success(next ? 'Featured on the home page' : 'Removed from featured')
  } catch {
    featured.value = !next
    toast.error('Failed to update featured state')
  } finally {
    busy.value = false
  }
}

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

const onVisibilityUpdated = (v: Visibility) => {
  // Let the parent reflect the change (the request object it owns drives the
  // visibility badge); we avoid mutating the prop directly here.
  emit('visibility-change', v)
}
</script>

<template>
  <div class="flex items-center gap-1" @click.stop>
    <!-- Retry (owner only, failed requests only) -->
    <Button
      v-if="retryable"
      variant="ghost"
      size="sm"
      class="h-8 px-2 gap-1 text-muted-foreground hover:text-foreground"
      :disabled="retrying"
      title="Retry this request"
      @click="onRetry"
    >
      <component :is="retrying ? Loader2 : RotateCcw" class="size-4" :class="retrying ? 'animate-spin' : ''" />
      <span class="text-xs">{{ retrying ? 'Retrying…' : 'Retry' }}</span>
    </Button>

    <!-- Star (read-only count for logged-out visitors; interactive once signed
         in — writes would 403 anyway, so the button is a sign-in dead end). -->
    <Button
      v-if="isAuthenticated"
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
    <span
      v-else-if="starCount > 0"
      class="flex h-8 items-center gap-1 px-2 text-muted-foreground"
      :title="`${starCount} stars`"
    >
      <Star class="size-4" />
      <span class="text-xs tabular-nums">{{ starCount }}</span>
    </span>

    <!-- Bookmark (signed-in only) -->
    <Button
      v-if="isAuthenticated"
      variant="ghost"
      size="icon"
      class="size-8"
      :class="bookmarked ? 'text-primary' : 'text-muted-foreground'"
      :title="bookmarked ? 'Remove bookmark' : 'Bookmark to your profile'"
      @click="onBookmark"
    >
      <Bookmark class="size-4" :class="bookmarked ? 'fill-current' : ''" />
    </Button>

    <!-- Feature on the home page (staff only, PUBLIC requests only). Inline only
         in the expanded layout; dense mode folds it into the ⋯ menu. -->
    <Button
      v-if="canFeature && !dense"
      variant="ghost"
      size="icon"
      class="size-8"
      :class="featured ? 'text-emerald-500' : 'text-muted-foreground'"
      :title="featured ? 'Remove from home-page featured' : 'Feature on the home page'"
      data-testid="feature-toggle"
      @click="onFeature"
    >
      <Megaphone class="size-4" :class="featured ? 'fill-current' : ''" />
    </Button>

    <!-- Share (owner only — only the owner is given the share_token). Inline in
         the expanded layout; dense mode folds it into the ⋯ menu as a submenu. -->
    <ShareMenu v-if="shareable && !dense" :request="request" />

    <!-- Owner menu: visibility + collections, plus (dense) share/feature/delete -->
    <DropdownMenu v-if="request.is_owner">
      <DropdownMenuTrigger as-child>
        <Button variant="ghost" size="icon" class="size-8 text-muted-foreground" title="More">
          <MoreHorizontal class="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-52">
        <!-- Dense: share lives here as a submenu -->
        <template v-if="dense && shareable">
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <Share2 class="size-4" /> Share
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem @select="copyShareLink">
                <LinkIcon class="size-4" /> Copy link
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem @select="shareToX">
                <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
                Share on X
              </DropdownMenuItem>
              <DropdownMenuItem @select="shareToReddit">
                <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z" />
                </svg>
                Share on Reddit
              </DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </template>

        <DropdownMenuItem @select="visEditOpen = true">
          <Eye class="size-4" /> Edit visibility
        </DropdownMenuItem>
        <DropdownMenuItem @select="collectOpen = true">
          <FolderPlus class="size-4" /> Add to collection
        </DropdownMenuItem>
        <DropdownMenuItem v-if="isTrack" @select="coverOpen = true">
          <Palette class="size-4" /> Generate cover art
        </DropdownMenuItem>

        <!-- Dense: feature toggle folds in here -->
        <DropdownMenuItem v-if="dense && canFeature" @select="onFeature">
          <Megaphone class="size-4" :class="featured ? 'text-emerald-500' : ''" />
          {{ featured ? 'Unfeature' : 'Feature on home' }}
        </DropdownMenuItem>

        <!-- Dense: delete folds in here (host handles the emit) -->
        <template v-if="dense && canDelete">
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" :disabled="deleting" @select="deleteOpen = true">
            <Trash2 class="size-4" /> Delete
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>

    <!-- Report (non-owners only — you don't report your own content) -->
    <Button
      v-if="!request.is_owner && isAuthenticated"
      variant="ghost"
      size="icon"
      class="size-8 text-muted-foreground hover:text-destructive"
      title="Report"
      @click="reportOpen = true"
    >
      <Flag class="size-4" />
    </Button>

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
    <GenerateCoverDialog
      v-if="request.is_owner && isTrack"
      v-model:open="coverOpen"
      :target="{ kind: 'request', id: request.id }"
      :seed-prompt="coverSeed"
    />
    <ReportDialog
      v-if="!request.is_owner && isAuthenticated"
      v-model:open="reportOpen"
      :request="request"
    />

    <!-- Delete confirmation (dense card menu only — host performs the delete) -->
    <AlertDialog v-if="dense && canDelete" v-model:open="deleteOpen">
      <AlertDialogContent @click.stop>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes this request and its stored prompt and
            response. This can't be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-white hover:bg-destructive/90"
            @click="emit('delete')"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
