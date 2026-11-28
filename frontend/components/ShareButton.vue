<script setup lang="ts">
// Share any link: the phone's share sheet where there is one, otherwise a
// small menu (copy, X, Reddit). Defaults to the page being viewed, so anyone
// looking at a shared page can pass it on.
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Share2, Link as LinkIcon, Check } from 'lucide-vue-next'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = withDefaults(
  defineProps<{
    /** Link to share; the current page when omitted. */
    url?: string
    /** Text that goes with the link. */
    text?: string
    variant?: 'default' | 'outline' | 'secondary' | 'ghost'
    size?: 'default' | 'sm'
    /** Hide the word and show only the icon. */
    iconOnly?: boolean
  }>(),
  { url: '', text: '', variant: 'outline', size: 'sm', iconOnly: false },
)

const { t } = useI18n()
const link = () => props.url || (typeof window !== 'undefined' ? window.location.href : '')
const copied = ref(false)
// Touch devices get the native sheet; desktops get the menu (their native
// share dialogs are poor).
const native = computed(
  () =>
    typeof navigator !== 'undefined' &&
    typeof navigator.share === 'function' &&
    typeof window !== 'undefined' &&
    window.matchMedia?.('(pointer: coarse)').matches,
)

const copy = async () => {
  const value = link()
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    // Clipboard API is blocked on plain http and in some webviews.
    const ta = document.createElement('textarea')
    ta.value = value
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    if (!ok) {
      toast.error(t('share.copyFailed'))
      return
    }
  }
  copied.value = true
  toast.success(t('share.copied'))
  setTimeout(() => (copied.value = false), 1500)
}

const nativeShare = async () => {
  try {
    await navigator.share({ url: link(), text: props.text || undefined })
  } catch {
    // Dismissed by the person: nothing to do.
  }
}

const open = (base: string, textKey: string) =>
  window.open(
    `${base}url=${encodeURIComponent(link())}&${textKey}=${encodeURIComponent(props.text)}`,
    '_blank',
    'noopener,noreferrer',
  )
</script>

<template>
  <Button
    v-if="native"
    :variant="variant"
    :size="iconOnly ? 'icon' : size"
    :class="iconOnly ? 'size-8' : 'gap-2'"
    :aria-label="t('share.share')"
    data-testid="share-button"
    @click="nativeShare"
  >
    <Share2 class="size-4" /> <span v-if="!iconOnly">{{ t('share.share') }}</span>
  </Button>
  <DropdownMenu v-else>
    <DropdownMenuTrigger as-child>
      <Button
        :variant="variant"
        :size="iconOnly ? 'icon' : size"
        :class="iconOnly ? 'size-8' : 'gap-2'"
        :aria-label="t('share.share')"
        data-testid="share-button"
      >
        <Share2 class="size-4" /> <span v-if="!iconOnly">{{ t('share.share') }}</span>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-48">
      <DropdownMenuItem data-testid="share-copy" @select="copy">
        <component :is="copied ? Check : LinkIcon" class="size-4" /> {{ t('share.copyLink') }}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @select="open('https://x.com/intent/tweet?', 'text')">
        <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
        {{ t('share.onX') }}
      </DropdownMenuItem>
      <DropdownMenuItem @select="open('https://www.reddit.com/submit?', 'title')">
        <svg class="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
        </svg>
        {{ t('share.onReddit') }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
