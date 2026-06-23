<script setup lang="ts">
// The per-row "⋮" overflow menu for a song: everything that doesn't fit inline
// (star/bookmark stay inline in RequestQuickActions). Owner-only actions
// (visibility, cover art, regenerate) are gated on `is_owner`; Feature is
// staff-only. Reuses the existing AddToCollectionDialog + GenerateCoverDialog.

import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  MoreVertical, ListPlus, ImagePlus, RefreshCw, Link2, Star,
  Globe, Eye, Lock, Check,
} from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { usePlaygroundPrefill, REPRODUCE_ROUTES } from '@/composables/usePlaygroundPrefill'
import { useAuth } from '@/composables/useAuth'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'

const props = defineProps<{ request: InferenceRequest }>()

const { updateVisibility, toggleFeatured, shareUrl } = useContentSharing()
const { getInferenceRequest } = useInferenceRequest()
const prefill = usePlaygroundPrefill()
const { user } = useAuth()

const showAddToPlaylist = ref(false)
const showCover = ref(false)
const busy = ref(false)

// Local, optimistic state seeded from the request (resynced when the row swaps),
// mirroring RequestQuickActions — avoids mutating the shared prop object.
const visibility = ref(props.request.visibility)
const featured = ref(!!props.request.is_featured)

watch(
  () => props.request.id,
  () => {
    visibility.value = props.request.visibility
    featured.value = !!props.request.is_featured
  },
)

const VIS_OPTIONS: { value: Visibility; label: string; icon: unknown }[] = [
  { value: 'PUBLIC', label: 'Public', icon: Globe },
  { value: 'UNLISTED', label: 'Unlisted', icon: Eye },
  { value: 'PRIVATE', label: 'Members only', icon: Lock },
]

const setVisibility = async (v: Visibility) => {
  if (busy.value || visibility.value === v) return
  busy.value = true
  const prev = visibility.value
  visibility.value = v // optimistic
  try {
    await updateVisibility(props.request.id, v)
    toast.success(`Visibility set to ${v.toLowerCase()}`)
  } catch {
    visibility.value = prev
    toast.error('Failed to update visibility')
  } finally {
    busy.value = false
  }
}

const onFeature = async () => {
  if (busy.value) return
  busy.value = true
  const next = !featured.value
  featured.value = next
  try {
    await toggleFeatured(props.request.id, next)
    toast.success(next ? 'Featured on the showcase' : 'Removed from showcase')
  } catch {
    featured.value = !next
    toast.error('Failed to update featured')
  } finally {
    busy.value = false
  }
}

const copyLink = async () => {
  const token = props.request.share_token
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const url = token
    ? shareUrl(token)
    : `${origin}/dashboard/inference/requests/${props.request.public_id ?? props.request.id}`
  try {
    await navigator.clipboard.writeText(url)
    toast.success('Link copied')
  } catch {
    toast.error('Could not copy link')
  }
}

// Regenerate = open the music composer pre-filled with this song's params.
// The full payload only comes back on the detail endpoint, so fetch it first.
const regenerate = async () => {
  const route = REPRODUCE_ROUTES[props.request.inference_type]
  if (!route) return
  try {
    const detail = await getInferenceRequest(
      String(props.request.public_id ?? props.request.id),
    )
    prefill.set(props.request.inference_type, {
      ...((detail?.payload as Record<string, unknown>) || {}),
      model: detail?.model_name,
    })
    navigateTo(route)
  } catch {
    toast.error('Could not load this song to regenerate')
  }
}
</script>

<template>
  <div @click.stop>
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button
          variant="ghost"
          size="icon"
          class="size-7 text-muted-foreground"
          title="More"
          data-testid="song-row-menu"
        >
          <MoreVertical class="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-52">
        <DropdownMenuItem @select="showAddToPlaylist = true">
          <ListPlus class="mr-2 size-4" /> Add to playlist
        </DropdownMenuItem>

        <template v-if="request.is_owner">
          <DropdownMenuItem @select="showCover = true">
            <ImagePlus class="mr-2 size-4" />
            {{ request.cover_image_url ? 'Change cover art' : 'Add cover art' }}
          </DropdownMenuItem>
          <DropdownMenuItem @select="regenerate">
            <RefreshCw class="mr-2 size-4" /> Regenerate
          </DropdownMenuItem>
        </template>

        <DropdownMenuItem @select="copyLink">
          <Link2 class="mr-2 size-4" /> Copy link
        </DropdownMenuItem>

        <template v-if="request.is_owner">
          <DropdownMenuSeparator />
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <Eye class="mr-2 size-4" /> Visibility
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem
                v-for="opt in VIS_OPTIONS"
                :key="opt.value"
                @select="setVisibility(opt.value)"
              >
                <component :is="opt.icon" class="mr-2 size-4" />
                {{ opt.label }}
                <Check
                  v-if="visibility === opt.value"
                  class="ml-auto size-4"
                />
              </DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </template>

        <template v-if="user?.is_staff">
          <DropdownMenuSeparator />
          <DropdownMenuItem @select="onFeature">
            <Star
              class="mr-2 size-4"
              :class="featured ? 'fill-current text-amber-500' : ''"
            />
            {{ featured ? 'Unfeature' : 'Feature on showcase' }}
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>

    <AddToCollectionDialog
      v-model:open="showAddToPlaylist"
      :request="request"
    />
    <GenerateCoverDialog
      v-model:open="showCover"
      :target="{ kind: 'request', id: request.id }"
      :seed-prompt="request.prompt_preview"
    />
  </div>
</template>
