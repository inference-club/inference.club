<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ExternalLink, EyeOff, Trash2, Check, X, Flag } from 'lucide-vue-next'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useAdmin, type ContentReport, type ReportStatus } from '@/composables/useAdmin'

definePageMeta({
  layout: 'app',
  middleware: 'staff',
})

const { listReports, updateReport, moderateRequest, loading, error } = useAdmin()

const reports = ref<ContentReport[]>([])
const filter = ref<'open' | 'all' | ReportStatus>('open')
const busyId = ref<number | null>(null)

const FILTERS: { value: 'open' | 'all' | ReportStatus; label: string }[] = [
  { value: 'open', label: 'Needs review' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'DISMISSED', label: 'Dismissed' },
  { value: 'all', label: 'All' },
]

const load = async () => {
  try {
    const res = await listReports(filter.value)
    reports.value = res.results
  } catch {
    // surfaced via `error`
  }
}

const setFilter = (f: typeof filter.value) => {
  filter.value = f
  load()
}

onMounted(load)

const triage = async (r: ContentReport, status: ReportStatus) => {
  busyId.value = r.id
  try {
    await updateReport(r.id, { status })
    toast.success(status === 'RESOLVED' ? 'Report resolved' : 'Report dismissed')
    await load()
  } catch {
    toast.error('Failed to update report')
  } finally {
    busyId.value = null
  }
}

const hide = async (r: ContentReport) => {
  busyId.value = r.id
  try {
    await moderateRequest(r.request.id, 'hide')
    toast.success('Content hidden (set to “Only me”)')
    await load()
  } catch {
    toast.error('Failed to hide content')
  } finally {
    busyId.value = null
  }
}

const remove = async (r: ContentReport) => {
  busyId.value = r.id
  try {
    await moderateRequest(r.request.id, 'delete')
    toast.success('Content deleted')
    await load()
  } catch {
    toast.error('Failed to delete content')
  } finally {
    busyId.value = null
  }
}

const statusVariant = (s: ReportStatus) =>
  s === 'OPEN' ? 'destructive'
    : s === 'REVIEWING' ? 'default'
      : 'secondary'

const fmtDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-4 sm:px-6 py-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold">Moderation</h1>
      <p class="text-muted-foreground text-sm mt-1">
        Reports filed against inference requests. Resolve or dismiss the report,
        and take the content down when needed.
      </p>
    </div>

    <!-- Filter tabs -->
    <div class="flex flex-wrap gap-1">
      <Button
        v-for="f in FILTERS"
        :key="f.value"
        :variant="filter === f.value ? 'default' : 'outline'"
        size="sm"
        @click="setFilter(f.value)"
      >
        {{ f.label }}
      </Button>
    </div>

    <div v-if="loading && !reports.length" class="space-y-3">
      <Card v-for="i in 3" :key="i" class="p-4 h-32 animate-pulse" />
    </div>

    <div v-else-if="error" class="text-destructive text-sm py-8 text-center">
      {{ error }}
    </div>

    <div
      v-else-if="!reports.length"
      class="text-center py-16 text-muted-foreground"
    >
      <Flag class="size-8 mx-auto mb-3 opacity-40" />
      <p class="text-sm">No reports {{ filter === 'open' ? 'need review' : 'here' }}.</p>
    </div>

    <div v-else class="space-y-4">
      <Card v-for="r in reports" :key="r.id" class="p-4 space-y-3">
        <!-- Header: reason + status -->
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" class="gap-1">
              <Flag class="size-3" /> {{ r.reason_display }}
            </Badge>
            <Badge :variant="statusVariant(r.status)">{{ r.status_display }}</Badge>
            <span class="text-xs text-muted-foreground">
              reported by {{ r.reporter ?? 'unknown' }} · {{ fmtDate(r.created_on) }}
            </span>
          </div>
        </div>

        <!-- Reporter's note -->
        <p v-if="r.details" class="text-sm bg-muted/50 rounded p-2 italic">
          “{{ r.details }}”
        </p>

        <!-- Reported request preview -->
        <div class="rounded border bg-muted/30 p-3 space-y-1.5">
          <div class="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
            <Badge variant="secondary" class="h-5">{{ r.request.inference_type }}</Badge>
            <span class="font-mono">{{ r.request.model_name || '—' }}</span>
            <span>·</span>
            <span>owner: {{ r.request.owner }}</span>
            <span>·</span>
            <span>visibility: {{ r.request.visibility }}</span>
          </div>
          <p class="text-sm line-clamp-3 whitespace-pre-wrap">
            {{ r.request.prompt_preview || '(no preview)' }}
          </p>
          <NuxtLink
            :to="`/dashboard/inference/requests/${r.request.id}`"
            class="text-xs text-primary hover:underline inline-flex items-center gap-1"
          >
            <ExternalLink class="size-3" /> Open request #{{ r.request.id }}
          </NuxtLink>
        </div>

        <!-- Resolution note (if any) -->
        <p v-if="r.resolution_note" class="text-xs text-muted-foreground">
          Resolution: {{ r.resolution_note }}
          <template v-if="r.resolved_by"> — by {{ r.resolved_by }}</template>
        </p>

        <!-- Actions -->
        <div class="flex flex-wrap items-center gap-2 pt-1">
          <Button
            size="sm"
            variant="outline"
            :disabled="busyId === r.id"
            @click="triage(r, 'RESOLVED')"
          >
            <Check class="size-4" /> Resolve
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="busyId === r.id"
            @click="triage(r, 'DISMISSED')"
          >
            <X class="size-4" /> Dismiss
          </Button>

          <div class="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              :disabled="busyId === r.id"
              @click="hide(r)"
            >
              <EyeOff class="size-4" /> Hide content
            </Button>

            <AlertDialog>
              <AlertDialogTrigger as-child>
                <Button
                  size="sm"
                  variant="outline"
                  class="text-destructive hover:text-destructive"
                  :disabled="busyId === r.id"
                >
                  <Trash2 class="size-4" /> Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently removes request #{{ r.request.id }} (its prompt,
                    response, and all reports against it). This can't be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    class="bg-destructive text-white hover:bg-destructive/90"
                    @click="remove(r)"
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
