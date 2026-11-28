<script setup lang="ts">
// Share a collection by link. A shared collection is only whole when
// everything inside can be seen by a link holder, so the dialog says how many
// items cannot be, and sharing raises those to "anyone with the link".
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Link as LinkIcon, Check, Globe, EyeOff, Loader2, TriangleAlert } from 'lucide-vue-next'
import type { Collection } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{ open: boolean; collection: Collection }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'changed', c: Collection): void
}>()

const { t } = useI18n()
const { shareCollection, updateCollection, collectionShareUrl } = useContentSharing()

const shared = computed(() => ['PUBLIC', 'UNLISTED'].includes(props.collection.visibility))
const blocked = computed(() => props.collection.unshareable_count ?? 0)
const link = computed(() => collectionShareUrl(props.collection.share_token))
const busy = ref(false)
const copied = ref(false)

const share = async (visibility: 'UNLISTED' | 'PUBLIC') => {
  if (busy.value) return
  busy.value = true
  try {
    const res = await shareCollection(props.collection.slug, { visibility, includeItems: true })
    emit('changed', res)
    toast.success(
      res.items_raised
        ? t('collectionShare.sharedRaised', { n: res.items_raised }, res.items_raised)
        : t('collectionShare.shared'),
    )
  } catch {
    toast.error(t('collectionShare.failed'))
  } finally {
    busy.value = false
  }
}

const stop = async () => {
  if (busy.value) return
  busy.value = true
  try {
    const res = await updateCollection(props.collection.slug, { visibility: 'SECRET' })
    emit('changed', { ...props.collection, ...res })
    toast.success(t('collectionShare.stopped'))
  } catch {
    toast.error(t('collectionShare.failed'))
  } finally {
    busy.value = false
  }
}

const copy = async () => {
  try {
    await navigator.clipboard.writeText(link.value)
    copied.value = true
    toast.success(t('share.copied'))
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    toast.error(t('share.copyFailed'))
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader data-testid="share-collection-dialog">
        <DialogTitle>{{ t('collectionShare.title') }}</DialogTitle>
        <DialogDescription>
          {{ shared ? t('collectionShare.isShared') : t('collectionShare.notShared') }}
        </DialogDescription>
      </DialogHeader>

      <!-- Items a link holder would not see -->
      <div
        v-if="blocked > 0"
        class="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm"
        data-testid="share-collection-blocked"
      >
        <TriangleAlert class="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <p class="min-w-0">
          {{ t('collectionShare.blocked', { n: blocked }, blocked) }}
          {{ t('collectionShare.blockedFix') }}
        </p>
      </div>

      <!-- The link -->
      <div v-if="shared" class="flex min-w-0 items-center gap-2">
        <input
          :value="link"
          readonly
          class="h-9 min-w-0 flex-1 rounded-md border bg-muted/40 px-3 text-sm"
          data-testid="share-collection-link"
          @focus="($event.target as HTMLInputElement).select()"
        />
        <Button size="sm" class="shrink-0 gap-2" @click="copy">
          <component :is="copied ? Check : LinkIcon" class="size-4" /> {{ t('share.copyLink') }}
        </Button>
      </div>

      <div class="flex flex-col gap-2">
        <Button
          v-if="!shared || blocked > 0"
          class="justify-start gap-2"
          :disabled="busy"
          data-testid="share-collection-link-only"
          @click="share(collection.visibility === 'PUBLIC' ? 'PUBLIC' : 'UNLISTED')"
        >
          <component :is="busy ? Loader2 : LinkIcon" class="size-4" :class="busy ? 'animate-spin' : ''" />
          {{ blocked > 0 ? t('collectionShare.shareAll') : t('collectionShare.shareLink') }}
        </Button>
        <Button
          v-if="collection.visibility !== 'PUBLIC'"
          variant="outline"
          class="justify-start gap-2"
          :disabled="busy"
          data-testid="share-collection-public"
          @click="share('PUBLIC')"
        >
          <Globe class="size-4" /> {{ t('collectionShare.sharePublic') }}
        </Button>
        <Button
          v-if="shared"
          variant="ghost"
          class="justify-start gap-2 text-muted-foreground"
          :disabled="busy"
          data-testid="share-collection-stop"
          @click="stop"
        >
          <EyeOff class="size-4" /> {{ t('collectionShare.stop') }}
        </Button>
      </div>
      <p class="text-xs text-muted-foreground">{{ t('collectionShare.note') }}</p>
    </DialogContent>
  </Dialog>
</template>
