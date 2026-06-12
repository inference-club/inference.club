<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Globe, Link2, Users, Lock, Check, Copy } from 'lucide-vue-next'
import type { InferenceRequest, Visibility } from '@/types'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'
import { useContentSharing } from '@/composables/useContentSharing'
import { useAuth } from '@/composables/useAuth'

const props = defineProps<{ open: boolean; request: InferenceRequest }>()

// Anonymous (guest/passcode) accounts can never publish publicly; the API
// rejects it too — this just explains instead of erroring.
const { isAnonymous } = useAuth()
const isDisabled = (v: Visibility) => v === 'PUBLIC' && isAnonymous.value
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'updated', v: Visibility): void
}>()

const { updateVisibility, shareUrl } = useContentSharing()

const ICONS: Record<Visibility, typeof Globe> = {
  PUBLIC: Globe,
  UNLISTED: Link2,
  PRIVATE: Users,
  SECRET: Lock,
}

const selected = ref<Visibility>(props.request.visibility ?? 'UNLISTED')
const saving = ref(false)

watch(
  () => props.open,
  (o) => {
    if (o) selected.value = props.request.visibility ?? 'UNLISTED'
  },
)

const link = computed(() => shareUrl(props.request.share_token))
const linkShareable = computed(() => selected.value !== 'SECRET')

const copyLink = async () => {
  if (!link.value) return
  try {
    await navigator.clipboard.writeText(link.value)
    toast.success('Link copied')
  } catch {
    toast.error('Could not copy link')
  }
}

const save = async () => {
  if (selected.value === props.request.visibility) {
    emit('update:open', false)
    return
  }
  saving.value = true
  try {
    await updateVisibility(props.request.id, selected.value)
    emit('updated', selected.value)
    emit('update:open', false)
    toast.success('Visibility updated')
  } catch {
    toast.error('Failed to update visibility')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Who can see this?</DialogTitle>
        <DialogDescription>
          Control who can view request #{{ request.id }}.
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-2">
        <button
          v-for="v in VISIBILITY_ORDER"
          :key="v"
          type="button"
          class="w-full text-left rounded-lg border p-3 transition-colors"
          :class="[
            selected === v ? 'border-primary bg-primary/[0.04] ring-1 ring-primary/30' : 'hover:bg-muted/50',
            isDisabled(v) ? 'opacity-50 cursor-not-allowed hover:bg-transparent' : '',
          ]"
          :disabled="isDisabled(v)"
          @click="!isDisabled(v) && (selected = v)"
        >
          <div class="flex items-start gap-3">
            <component :is="ICONS[v]" class="size-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div class="min-w-0 flex-1">
              <div class="font-medium text-sm">{{ VISIBILITY_META[v].label }}</div>
              <p class="text-xs text-muted-foreground mt-0.5">
                {{ isDisabled(v) ? 'Anonymous accounts can\'t publish publicly.' : VISIBILITY_META[v].description }}
              </p>
            </div>
            <span
              class="flex size-4 shrink-0 items-center justify-center rounded-full mt-0.5"
              :class="selected === v ? 'bg-primary text-primary-foreground' : 'border'"
            >
              <Check v-if="selected === v" class="size-3" />
            </span>
          </div>
        </button>
      </div>

      <!-- Share link (hidden for "Only me") -->
      <div v-if="linkShareable && link" class="flex items-center gap-2">
        <Input :model-value="link" readonly class="font-mono text-xs" @focus="(e: FocusEvent) => (e.target as HTMLInputElement).select()" />
        <Button variant="outline" size="icon" class="shrink-0" aria-label="Copy link" @click="copyLink">
          <Copy class="size-4" />
        </Button>
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="emit('update:open', false)">Cancel</Button>
        <Button :disabled="saving" @click="save">Save</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
