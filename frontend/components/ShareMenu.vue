<script setup lang="ts">
import { computed } from 'vue'
import { toast } from 'vue-sonner'
import { Share2, Link as LinkIcon, ExternalLink } from 'lucide-vue-next'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import type { InferenceRequest } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{ request: InferenceRequest }>()

const { shareUrl } = useContentSharing()

// The canonical, unguessable share link (/s/<token>). Owner-only, since only
// the owner is given the share_token by the API.
const link = computed(() => shareUrl(props.request.share_token))

const shareText = computed(() => {
  const m = props.request.model_name
  return m ? `Inference with ${m} on inference.club` : 'Check out this inference on inference.club'
})

const copyLink = async () => {
  if (!link.value) return
  try {
    await navigator.clipboard.writeText(link.value)
    toast.success('Share link copied')
    return
  } catch {
    // Clipboard API can be blocked (permissions / insecure context) — fall
    // back to a hidden textarea + execCommand so copy still works.
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = link.value
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    document.execCommand('copy')
    ta.remove()
    toast.success('Share link copied')
  } catch {
    toast.error('Could not copy link')
  }
}

const openIntent = (url: string) => {
  window.open(url, '_blank', 'noopener,noreferrer')
}

const shareToX = () => {
  if (!link.value) return
  openIntent(
    `https://x.com/intent/tweet?url=${encodeURIComponent(link.value)}` +
    `&text=${encodeURIComponent(shareText.value)}`,
  )
}

const shareToReddit = () => {
  if (!link.value) return
  openIntent(
    `https://www.reddit.com/submit?url=${encodeURIComponent(link.value)}` +
    `&title=${encodeURIComponent(shareText.value)}`,
  )
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="size-8 text-muted-foreground"
        title="Share"
        @click.stop
      >
        <Share2 class="size-4" />
        <span class="sr-only">Share</span>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-44" @click.stop>
      <DropdownMenuLabel>Share</DropdownMenuLabel>
      <DropdownMenuItem @select="copyLink">
        <LinkIcon class="size-4" /> Copy link
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @select="shareToX">
        <!-- X (formerly Twitter) wordmark -->
        <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
        Share on X
      </DropdownMenuItem>
      <DropdownMenuItem @select="shareToReddit">
        <!-- Reddit mark -->
        <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z" />
        </svg>
        Share on Reddit
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
