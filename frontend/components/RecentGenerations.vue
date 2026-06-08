<script setup lang="ts">
// A shared, on-demand "recent for this model" strip for the playground pages.
// Given the active model + modality, it lists the signed-in user's most recent
// matching inference requests and renders each through InferenceRequestCard — so
// every modality (audio player, image grid, 3D viewer, transcript preview)
// displays consistently and the result plumbing lives in exactly one place.
//
// It does NOT load on mount: the user reveals it with a button (cheap default,
// no surprise fetch). Once open it paginates (a few per page). When a generation
// finishes the page bumps `refreshKey`; we auto-open, jump to the first page,
// and flash the card that just landed.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { ChevronLeft, ChevronRight, History, Loader2 } from 'lucide-vue-next'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import type { InferenceRequest, InferenceType } from '@/types'

const props = withDefaults(
  defineProps<{
    model: string
    type: InferenceType
    refreshKey?: number
    title?: string
    limit?: number
  }>(),
  { refreshKey: 0, title: 'Recent', limit: 3 },
)

const { listInferenceRequests, deleteInferenceRequest } = useInferenceRequest()

const open = ref(false)
const items = ref<InferenceRequest[]>([])
const loading = ref(false)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / props.limit)))

// The id of the card to flash (the one that just finished). Cleared after the
// animation so a re-render doesn't replay it.
const flashId = ref<string | null>(null)
let flashTimer: ReturnType<typeof setTimeout> | null = null

const flashNewest = () => {
  flashId.value = items.value[0] ? String(items.value[0].id) : null
  if (flashTimer) clearTimeout(flashTimer)
  if (flashId.value) flashTimer = setTimeout(() => (flashId.value = null), 2000)
}

const load = async ({ flash = false } = {}) => {
  if (!props.model) {
    items.value = []
    total.value = 0
    return
  }
  loading.value = true
  error.value = ''
  try {
    const offset = (page.value - 1) * props.limit
    const res = await listInferenceRequests(props.limit, offset, {
      type: props.type,
      model: props.model,
    })
    items.value = res.results
    total.value = res.count
    if (flash && page.value === 1) flashNewest()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load recent generations'
  } finally {
    loading.value = false
  }
}

const reveal = () => {
  open.value = true
  page.value = 1
  load()
}

const goTo = (p: number) => {
  if (p < 1 || p > pageCount.value || p === page.value || loading.value) return
  page.value = p
  flashId.value = null
  load()
}

const remove = async (id: string) => {
  try {
    await deleteInferenceRequest(id)
    // Step back a page if we just emptied the last one.
    if (items.value.length === 1 && page.value > 1) page.value--
    await load()
  } catch {
    toast.error('Failed to delete request')
  }
}

// Model switch → reset; reload only if already open. Never auto-opens.
watch(
  () => props.model,
  () => {
    page.value = 1
    flashId.value = null
    if (open.value) load()
  },
)

// Generation finished → reveal, jump to the newest, and flash it.
watch(
  () => props.refreshKey,
  (n, o) => {
    if (n === o) return
    open.value = true
    page.value = 1
    load({ flash: true })
  },
)

onBeforeUnmount(() => { if (flashTimer) clearTimeout(flashTimer) })
</script>

<template>
  <!-- Collapsed: a single button reveals the list (no fetch until asked). -->
  <Button v-if="!open" variant="outline" size="sm" class="gap-2" @click="reveal">
    <History class="size-4" /> {{ title }}
  </Button>

  <section v-else class="space-y-3">
    <div class="flex items-center justify-between">
      <button
        type="button"
        class="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground"
        @click="open = false"
      >
        <History class="size-4" /> {{ title }}
        <span v-if="total" class="font-normal">({{ total }})</span>
      </button>
      <NuxtLink
        to="/dashboard/inference/requests"
        class="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
      >
        View all
      </NuxtLink>
    </div>

    <p v-if="error" class="rounded-lg border border-dashed p-4 text-sm text-destructive">
      {{ error }}
    </p>

    <!-- Loading skeletons -->
    <div v-else-if="loading && !items.length" class="space-y-3">
      <div v-for="i in limit" :key="i" class="h-32 rounded-xl border bg-muted/50 animate-pulse" />
    </div>

    <p
      v-else-if="!items.length"
      class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground"
    >
      Nothing here yet — your generations with this model will show up here.
    </p>

    <template v-else>
      <TransitionGroup tag="div" name="rg" class="space-y-3" :class="{ 'opacity-60': loading }">
        <div
          v-for="item in items"
          :key="item.id"
          class="rounded-xl"
          :class="{ 'rg-flash': String(item.id) === flashId }"
        >
          <InferenceRequestCard :request="item" @delete="remove" />
        </div>
      </TransitionGroup>

      <!-- Pager -->
      <div v-if="pageCount > 1" class="flex items-center justify-center gap-3 text-sm">
        <Button variant="ghost" size="icon" class="size-8" :disabled="page <= 1 || loading" @click="goTo(page - 1)">
          <ChevronLeft class="size-4" />
        </Button>
        <span class="tabular-nums text-muted-foreground">
          <Loader2 v-if="loading" class="inline size-3.5 animate-spin" />
          <template v-else>{{ page }} / {{ pageCount }}</template>
        </span>
        <Button variant="ghost" size="icon" class="size-8" :disabled="page >= pageCount || loading" @click="goTo(page + 1)">
          <ChevronRight class="size-4" />
        </Button>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* Entrance + reflow for the list as new cards arrive. */
.rg-enter-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.rg-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}
.rg-leave-active {
  transition: opacity 0.3s ease;
  position: absolute;
}
.rg-leave-to {
  opacity: 0;
}
.rg-move {
  transition: transform 0.4s ease;
}

/* One-shot highlight on the card that just finished. */
.rg-flash {
  animation: rg-flash 2s ease-out;
}
@keyframes rg-flash {
  0% {
    box-shadow: 0 0 0 2px var(--primary);
    background-color: color-mix(in oklch, var(--primary) 8%, transparent);
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
    background-color: transparent;
  }
}
</style>
