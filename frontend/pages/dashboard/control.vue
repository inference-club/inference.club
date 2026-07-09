<script setup lang="ts">
/**
 * Cluster Control Center (PRD 21) — the single pane of glass for your GPU boxes.
 *
 * V0 is read-only: it shows only the GPU-schedulable boxes, each with its two
 * headline metrics (free VRAM + utilization), the services running on it, and
 * the parked services that could be started there. Park / Unpark / Start
 * controls are visible but disabled — actuation lands in V1.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import {
  Cpu, Server, Activity, MemoryStick, Play, Square, RefreshCw,
  AlertTriangle, CircleSlash, Boxes, Loader2,
} from 'lucide-vue-next'
import {
  useControlCenter, type ControlBoardPayload, type ControlBox,
  type ControlService, type ServiceState,
} from '@/composables/useControlCenter'
import ReadinessDot from '@/components/ReadinessDot.vue'

definePageMeta({ layout: 'app', requireAuth: true })

const { loadBoard } = useControlCenter()

const board = ref<ControlBoardPayload | null>(null)
const loading = ref(true)
const error = ref<'' | 'unauthorized' | 'failed'>('')

const load = async () => {
  try {
    board.value = await loadBoard()
    error.value = ''
  } catch (e: unknown) {
    error.value = (e as Error).message === 'unauthorized' ? 'unauthorized' : 'failed'
  } finally {
    loading.value = false
  }
}

// Live-ish: poll while the tab is open. The server caches cluster-state ~12s.
const { pause, resume } = useIntervalFn(load, 15000, { immediate: false })
onMounted(() => { load(); resume() })
onUnmounted(() => pause())

const providers = computed(() => board.value?.providers ?? [])
const isEmpty = computed(() => !loading.value && !error.value && providers.value.length === 0)

// ── formatting ─────────────────────────────────────────────────────────────
const gb = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)}`)
const pct = (v: number | null | undefined) => (v == null ? null : Math.round(v))

const vramFraction = (box: ControlBox) => {
  const { vram_used_gb: used, vram_total_gb: total } = box.gpu
  if (used == null || total == null || total <= 0) return 0
  return Math.min(1, Math.max(0, used / total))
}

// State → badge styling (richer than ReadinessDot's on/off).
const STATE_META: Record<ServiceState, { label: string; dot: string; text: string }> = {
  running: { label: 'running', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  starting: { label: 'starting', dot: 'bg-amber-500 animate-pulse', text: 'text-amber-600 dark:text-amber-400' },
  stopping: { label: 'stopping', dot: 'bg-amber-500 animate-pulse', text: 'text-amber-600 dark:text-amber-400' },
  parked: { label: 'parked', dot: 'bg-muted-foreground/40', text: 'text-muted-foreground' },
  failed: { label: 'failed', dot: 'bg-rose-500', text: 'text-rose-600 dark:text-rose-400' },
}

// Small color accent per service type for the type chip.
const TYPE_COLOR: Record<string, string> = {
  llm: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  stt: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  tts: 'bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-400',
  image: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  video: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  music: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  mesh: 'bg-teal-500/15 text-teal-600 dark:text-teal-400',
}
const typeChip = (t: string) => TYPE_COLOR[t] ?? 'bg-muted text-muted-foreground'

const fitMeta = (s: ControlService) => {
  if (s.fits === true) return { label: 'fits', cls: 'text-emerald-600 dark:text-emerald-400' }
  if (s.fits === false) return { label: "won't fit", cls: 'text-rose-600 dark:text-rose-400' }
  return { label: 'fit unknown', cls: 'text-muted-foreground' }
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 py-6 sm:px-6">
    <div class="mb-5 flex items-start justify-between gap-3">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-bold">
          <Cpu class="size-6 text-primary" /> Control center
        </h1>
        <p class="text-sm text-muted-foreground">
          Your GPU boxes at a glance — what's running, how much VRAM is free, and what fits.
        </p>
      </div>
      <button
        class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted"
        :disabled="loading" @click="load"
      >
        <RefreshCw class="size-3.5" :class="loading ? 'animate-spin' : ''" /> Refresh
      </button>
    </div>

    <!-- states -->
    <div v-if="loading && !board" class="py-16 text-center text-muted-foreground">
      <Loader2 class="mx-auto mb-2 size-6 animate-spin" /> Loading your cluster…
    </div>

    <div v-else-if="error === 'unauthorized'"
         class="rounded-lg border border-amber-400/60 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
      You need to be signed in as the cluster owner to use the control center.
    </div>

    <div v-else-if="error === 'failed'"
         class="flex items-start gap-2 rounded-lg border border-rose-400/60 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
      <AlertTriangle class="mt-0.5 size-4 shrink-0" />
      Couldn't load the control board. It will retry automatically.
    </div>

    <div v-else-if="isEmpty"
         class="rounded-lg border bg-background p-6 text-center text-sm text-muted-foreground">
      <Boxes class="mx-auto mb-2 size-6" />
      No cluster is opted in yet. Enable <span class="font-medium">cluster control</span> on one of
      your kubernetes providers to manage its inference services here.
    </div>

    <!-- boards -->
    <div v-for="p in providers" :key="p.provider.id" class="mb-8">
      <div class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <div class="flex items-center gap-2">
          <Server class="size-4 text-muted-foreground" />
          <span class="font-semibold">{{ p.provider.name }}</span>
          <ReadinessDot :online="p.provider.online" />
        </div>
        <span v-if="!p.provider.has_live_state"
              class="rounded bg-amber-500/15 px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400">
          no live telemetry — agent offline
        </span>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <!-- box card -->
        <div v-for="box in p.boxes" :key="box.box"
             class="rounded-xl border bg-card p-4"
             :class="box.schedulable ? '' : 'opacity-70'">
          <!-- header -->
          <div class="mb-3 flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-bold">{{ box.box }}</span>
                <span v-if="box.arch"
                      class="rounded bg-muted px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
                  {{ box.arch }}
                </span>
              </div>
              <div class="text-xs text-muted-foreground">
                {{ box.gpu.count }}× {{ box.gpu.model || 'GPU' }}
              </div>
            </div>
            <span v-if="box.schedulable"
                  class="rounded bg-emerald-500/15 px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
              schedulable
            </span>
            <span v-else
                  class="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
              <CircleSlash class="size-3" /> {{ box.unschedulable_reason || 'unavailable' }}
            </span>
          </div>

          <!-- headline metrics: free VRAM + utilization -->
          <div class="mb-3 grid grid-cols-2 gap-3">
            <div>
              <div class="mb-1 flex items-center gap-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
                <MemoryStick class="size-3" /> VRAM
              </div>
              <div class="text-sm">
                <span class="text-base font-bold">{{ gb(box.gpu.vram_free_gb) }}</span>
                <span class="text-muted-foreground"> GB free</span>
              </div>
              <div class="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div class="h-full rounded-full bg-primary"
                     :style="{ width: `${vramFraction(box) * 100}%` }" />
              </div>
              <div class="mt-0.5 text-2xs text-muted-foreground">
                {{ gb(box.gpu.vram_used_gb) }} / {{ gb(box.gpu.vram_total_gb) }} GB
                <span v-if="box.gpu.unified">· unified</span>
              </div>
            </div>
            <div>
              <div class="mb-1 flex items-center gap-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
                <Activity class="size-3" /> Utilization
              </div>
              <div class="text-sm">
                <span class="text-base font-bold">{{ pct(box.gpu.utilization_pct) ?? '—' }}</span>
                <span v-if="pct(box.gpu.utilization_pct) != null" class="text-muted-foreground">%</span>
              </div>
              <div class="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div class="h-full rounded-full bg-sky-500"
                     :style="{ width: `${pct(box.gpu.utilization_pct) ?? 0}%` }" />
              </div>
            </div>
          </div>

          <!-- running services -->
          <div v-if="box.services.length" class="space-y-1.5">
            <div v-for="s in box.services" :key="s.name"
                 class="flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5">
              <img v-if="s.logo_url" :src="s.logo_url" alt="" class="size-5 rounded object-contain" />
              <span v-else class="grid size-5 place-items-center rounded bg-muted text-2xs">
                {{ s.name.slice(0, 2) }}
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="truncate text-sm font-medium">{{ s.name }}</span>
                  <span class="rounded px-1 py-0.5 text-2xs font-semibold uppercase" :class="typeChip(s.type)">
                    {{ s.type }}
                  </span>
                </div>
                <div class="flex items-center gap-1.5 text-2xs">
                  <span class="inline-flex items-center gap-1" :class="STATE_META[s.state].text">
                    <span class="inline-block size-1.5 rounded-full" :class="STATE_META[s.state].dot" />
                    {{ STATE_META[s.state].label }}
                  </span>
                  <span v-if="s.live_vram_gb != null" class="text-muted-foreground">
                    · {{ gb(s.live_vram_gb) }} GB
                  </span>
                </div>
              </div>
              <button
                class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-2xs text-muted-foreground opacity-60"
                disabled title="Park / unpark ships in V1">
                <Square class="size-3" /> Stop
              </button>
            </div>
          </div>
          <div v-else class="rounded-lg border border-dashed px-2.5 py-3 text-center text-xs text-muted-foreground">
            Nothing running here
          </div>

          <!-- start here (parked, fits) -->
          <div v-if="box.startable.length" class="mt-3">
            <div class="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
              Start a service here
            </div>
            <div class="space-y-1.5">
              <div v-for="s in box.startable" :key="s.name"
                   class="flex items-center gap-2 rounded-lg border border-dashed bg-background/60 px-2.5 py-1.5">
                <img v-if="s.logo_url" :src="s.logo_url" alt="" class="size-5 rounded object-contain opacity-70" />
                <span v-else class="grid size-5 place-items-center rounded bg-muted text-2xs text-muted-foreground">
                  {{ s.name.slice(0, 2) }}
                </span>
                <div class="min-w-0 flex-1">
                  <span class="truncate text-sm">{{ s.name }}</span>
                  <div class="text-2xs">
                    <span :class="fitMeta(s).cls">{{ fitMeta(s).label }}</span>
                    <span class="text-muted-foreground">
                      · {{ s.expected_vram_gb != null ? gb(s.expected_vram_gb) + ' GB' : 'VRAM unknown' }}
                    </span>
                  </div>
                </div>
                <button
                  class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-2xs text-muted-foreground opacity-60"
                  disabled title="Park / unpark ships in V1">
                  <Play class="size-3" /> Start
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- parked services not tied to a shown box -->
      <div v-if="p.parked_elsewhere.length" class="mt-3 text-xs text-muted-foreground">
        <span class="font-medium">Parked (no box match):</span>
        {{ p.parked_elsewhere.map((s) => s.name).join(', ') }}
      </div>
    </div>

    <p v-if="providers.length" class="mt-2 text-2xs text-muted-foreground">
      Read-only preview — park / unpark and start controls activate in V1.
    </p>
  </div>
</template>
