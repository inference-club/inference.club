<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Map, CircleCheck, CircleDot, Circle, CircleSlash, FileText, History } from 'lucide-vue-next'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useAdmin, type Roadmap, type RoadmapStatus } from '@/composables/useAdmin'

definePageMeta({
  layout: 'app',
  middleware: 'staff',
})

const { getRoadmap, loading, error } = useAdmin()
const data = ref<Roadmap | null>(null)

const load = async () => {
  try {
    data.value = await getRoadmap()
  } catch {
    // surfaced via `error`
  }
}
onMounted(load)

// Status → presentation. Kept here (not i18n'd) since this is a staff-only
// internal tool; the PRD-12 public roadmap will localize its own copy.
const STATUS_META: Record<RoadmapStatus, { label: string; icon: any; cls: string; dot: string }> = {
  done: { label: 'Done', icon: CircleCheck, cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30', dot: 'bg-emerald-500' },
  in_progress: { label: 'In progress', icon: CircleDot, cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30', dot: 'bg-amber-500' },
  blocked: { label: 'Blocked', icon: CircleSlash, cls: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30', dot: 'bg-rose-500' },
  planned: { label: 'Planned', icon: Circle, cls: 'bg-muted text-muted-foreground border-border', dot: 'bg-muted-foreground/40' },
}
const sm = (s: RoadmapStatus) => STATUS_META[s] ?? STATUS_META.planned

const overallPct = computed(() => {
  const t = data.value?.totals
  if (!t || !t.tasks) return 0
  return Math.round((t.done / t.tasks) * 100)
})

const phasePct = (p: { progress: { total: number; done: number } }) =>
  p.progress.total ? Math.round((p.progress.done / p.progress.total) * 100) : 0

const trackLabel = (key: string) => data.value?.meta.tracks[key] ?? key

const fmtDay = (iso: string) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Map class="size-6" /> Roadmap
      </h1>
      <p class="text-muted-foreground text-sm mt-1">
        Media Pipeline &amp; Narration Studio programme (PRD 12). A staff-only,
        git-versioned tracker — edit
        <code class="text-xs">apps/inference/roadmap.py</code> to update.
      </p>
    </div>

    <div v-if="loading && !data" class="space-y-4">
      <Card v-for="i in 4" :key="i" class="p-4 h-28 animate-pulse" />
    </div>

    <div v-else-if="error" class="text-destructive text-sm py-8 text-center">
      {{ error }}
    </div>

    <template v-else-if="data">
      <!-- Overview -->
      <Card class="p-5 space-y-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="text-lg font-semibold">{{ data.meta.title }}</div>
            <a
              :href="`https://github.com/inference-club/inference.club/blob/main/${data.meta.prd}`"
              target="_blank" rel="noopener"
              class="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mt-0.5"
            >
              <FileText class="size-3.5" /> {{ data.meta.prd }}
            </a>
          </div>
          <div class="text-right">
            <div class="text-2xl font-bold tabular-nums">{{ overallPct }}%</div>
            <div class="text-xs text-muted-foreground">
              {{ data.totals.done }}/{{ data.totals.tasks }} tasks ·
              {{ data.totals.phases_done }}/{{ data.totals.phases }} phases
            </div>
          </div>
        </div>

        <p class="text-sm text-muted-foreground leading-relaxed">{{ data.meta.summary }}</p>

        <div class="h-2 w-full rounded-full bg-muted overflow-hidden">
          <div class="h-full bg-primary transition-all" :style="{ width: `${overallPct}%` }" />
        </div>

        <div class="flex flex-wrap gap-2 text-xs">
          <Badge v-for="(label, key) in data.meta.tracks" :key="key" variant="outline">
            Track {{ key }} — {{ label }}
          </Badge>
          <span class="text-muted-foreground ml-auto">Updated {{ fmtDay(data.meta.updated) }}</span>
        </div>
      </Card>

      <!-- Phases -->
      <section class="space-y-4">
        <Card v-for="p in data.phases" :key="p.id" class="p-5 space-y-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-xs font-mono font-semibold text-muted-foreground">{{ p.phase }}</span>
                <h2 class="text-base font-semibold">{{ p.title }}</h2>
                <Badge variant="outline" class="text-[10px]">{{ trackLabel(p.track) }}</Badge>
              </div>
              <p class="text-xs text-muted-foreground mt-1">
                <span class="font-medium text-foreground/70">Gate:</span> {{ p.gate }}
              </p>
            </div>
            <Badge variant="outline" :class="sm(p.status).cls" class="shrink-0 gap-1">
              <component :is="sm(p.status).icon" class="size-3" /> {{ sm(p.status).label }}
            </Badge>
          </div>

          <div class="flex items-center gap-3">
            <div class="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
              <div class="h-full bg-primary transition-all" :style="{ width: `${phasePct(p)}%` }" />
            </div>
            <span class="text-xs text-muted-foreground tabular-nums shrink-0">
              {{ p.progress.done }}/{{ p.progress.total }}
            </span>
          </div>

          <ul class="space-y-1.5">
            <li
              v-for="task in p.tasks" :key="task.id"
              class="flex items-start gap-2.5 text-sm py-1 border-t border-border/40 first:border-t-0"
            >
              <span class="mt-1.5 size-2 rounded-full shrink-0" :class="sm(task.status).dot" />
              <div class="min-w-0">
                <span :class="task.status === 'done' ? 'text-muted-foreground line-through' : ''">
                  {{ task.title }}
                </span>
                <p v-if="task.note" class="text-xs text-muted-foreground mt-0.5">{{ task.note }}</p>
              </div>
            </li>
          </ul>
        </Card>
      </section>

      <!-- Progress log -->
      <section v-if="data.progress_log?.length" class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
          <History class="size-4" /> Progress log
        </h2>
        <Card class="p-5">
          <ul class="space-y-3">
            <li v-for="(entry, i) in data.progress_log" :key="i" class="flex gap-3 text-sm">
              <span class="text-xs text-muted-foreground tabular-nums shrink-0 w-24">{{ fmtDay(entry.date) }}</span>
              <span class="text-muted-foreground leading-relaxed">{{ entry.note }}</span>
            </li>
          </ul>
        </Card>
      </section>
    </template>
  </div>
</template>
