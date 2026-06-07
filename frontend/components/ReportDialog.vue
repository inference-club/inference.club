<script setup lang="ts">
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Check } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{ open: boolean; request: InferenceRequest }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const { reportRequest } = useContentSharing()

// Mirrors REPORT_REASON_CHOICES in apps/inference/models.py.
const REASONS: { value: string; label: string }[] = [
  { value: 'SEXUAL', label: 'Sexual or explicit content' },
  { value: 'VIOLENCE', label: 'Violence or gore' },
  { value: 'HATE', label: 'Hate or harassment' },
  { value: 'ILLEGAL', label: 'Illegal or dangerous' },
  { value: 'CSAM', label: 'Child sexual abuse material' },
  { value: 'SPAM', label: 'Spam or misleading' },
  { value: 'OTHER', label: 'Other' },
]

const reason = ref<string>('')
const details = ref<string>('')
const submitting = ref(false)

watch(
  () => props.open,
  (o) => {
    if (o) {
      reason.value = ''
      details.value = ''
    }
  },
)

const submit = async () => {
  if (!reason.value) {
    toast.error('Pick a reason')
    return
  }
  submitting.value = true
  try {
    const res = await reportRequest(props.request.id, {
      reason: reason.value,
      details: details.value.trim(),
    })
    toast.success(
      res.already_reported
        ? 'You already reported this — thanks'
        : 'Report submitted — thank you',
    )
    emit('update:open', false)
  } catch {
    toast.error('Failed to submit report')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Report this request</DialogTitle>
        <DialogDescription>
          Flag request #{{ request.id }} for review by the moderation team. Reports
          are confidential.
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-2 max-h-[40vh] overflow-y-auto">
        <button
          v-for="r in REASONS"
          :key="r.value"
          type="button"
          class="w-full text-left rounded-lg border p-2.5 transition-colors flex items-center gap-3"
          :class="reason === r.value ? 'border-primary bg-primary/[0.04] ring-1 ring-primary/30' : 'hover:bg-muted/50'"
          @click="reason = r.value"
        >
          <span
            class="flex size-4 shrink-0 items-center justify-center rounded-full"
            :class="reason === r.value ? 'bg-primary text-primary-foreground' : 'border'"
          >
            <Check v-if="reason === r.value" class="size-3" />
          </span>
          <span class="text-sm">{{ r.label }}</span>
        </button>
      </div>

      <div class="space-y-1.5">
        <Label for="report-details">Details (optional)</Label>
        <Textarea
          id="report-details"
          v-model="details"
          placeholder="Add any context that helps a moderator review this."
          rows="3"
          maxlength="2000"
        />
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="destructive" :disabled="submitting || !reason" @click="submit">
          Submit report
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
