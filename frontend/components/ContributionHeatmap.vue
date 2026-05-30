<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// GitHub-style daily activity heatmap. Renders client-side (after mount) so the
// "today"-anchored grid can't cause an SSR/hydration mismatch.
const props = withDefaults(
  defineProps<{
    data: { date: string; count: number; tokens?: number }[]
    scheme?: 'emerald' | 'sky'
    weeks?: number
  }>(),
  { scheme: 'emerald', weeks: 53 }
)

// Full literal class strings so Tailwind's JIT picks them up. Index 0 = empty.
const SCHEMES: Record<string, string[]> = {
  emerald: [
    'bg-muted',
    'bg-emerald-200 dark:bg-emerald-900',
    'bg-emerald-400 dark:bg-emerald-700',
    'bg-emerald-500',
    'bg-emerald-600 dark:bg-emerald-300',
  ],
  sky: [
    'bg-muted',
    'bg-sky-200 dark:bg-sky-900',
    'bg-sky-400 dark:bg-sky-700',
    'bg-sky-500',
    'bg-sky-600 dark:bg-sky-300',
  ],
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAY = 86_400_000

const mounted = ref(false)
onMounted(() => {
  mounted.value = true
})

const counts = computed(() => {
  const m = new Map<string, number>()
  for (const d of props.data) m.set(d.date, d.count)
  return m
})

const maxCount = computed(() => props.data.reduce((mx, d) => Math.max(mx, d.count), 0))

const level = (count: number): number => {
  if (count <= 0 || maxCount.value <= 0) return 0
  const r = count / maxCount.value
  if (r > 0.66) return 4
  if (r > 0.33) return 3
  if (r > 0.1) return 2
  return 1
}

const fmt = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

type Cell = { date: string; count: number; level: number } | null

const grid = computed<Cell[][]>(() => {
  if (!mounted.value) return []
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const lastSunday = new Date(today.getTime() - today.getDay() * DAY)
  const firstSunday = new Date(lastSunday.getTime() - (props.weeks - 1) * 7 * DAY)
  const cols: Cell[][] = []
  for (let w = 0; w < props.weeks; w++) {
    const col: Cell[] = []
    for (let d = 0; d < 7; d++) {
      const date = new Date(firstSunday.getTime() + (w * 7 + d) * DAY)
      if (date.getTime() > today.getTime()) {
        col.push(null)
        continue
      }
      const key = fmt(date)
      const count = counts.value.get(key) ?? 0
      col.push({ date: key, count, level: level(count) })
    }
    cols.push(col)
  }
  return cols
})

// Month label at the column where a new month starts — but skip labels that
// would sit within 3 columns of the previous one (avoids "MayJun" collisions
// at the left edge / on the partial first month).
const monthByCol = computed<Record<number, string>>(() => {
  const out: Record<number, string> = {}
  let lastMonth = -1
  let lastCol = -99
  grid.value.forEach((col, i) => {
    const first = col.find(Boolean) as { date: string } | undefined
    if (!first) return
    const month = Number(first.date.slice(5, 7)) - 1
    if (month !== lastMonth) {
      if (i - lastCol >= 3) {
        out[i] = MONTHS[month]
        lastCol = i
      }
      lastMonth = month
    }
  })
  return out
})

const total = computed(() => props.data.reduce((s, d) => s + d.count, 0))
</script>

<template>
  <div class="w-full">
    <div v-if="mounted">
      <!-- month labels (each slot matches a week column) -->
      <div class="flex gap-[3px] mb-1 text-[10px] text-muted-foreground">
        <div v-for="(_, i) in grid" :key="i" class="flex-1 min-w-0 h-3 relative">
          <span v-if="monthByCol[i]" class="absolute left-0 top-0 whitespace-nowrap">
            {{ monthByCol[i] }}
          </span>
        </div>
      </div>
      <!-- grid: columns flex to fill the container width, cells stay square -->
      <div class="flex gap-[3px]">
        <div
          v-for="(col, i) in grid"
          :key="i"
          class="flex-1 min-w-0 flex flex-col gap-[3px]"
        >
          <div
            v-for="(cell, d) in col"
            :key="d"
            class="aspect-square rounded-[2px]"
            :class="cell ? SCHEMES[scheme][cell.level] : 'bg-transparent'"
            :title="cell ? `${cell.count} request${cell.count === 1 ? '' : 's'} · ${cell.date}` : ''"
          />
        </div>
      </div>
      <!-- legend -->
      <div class="flex items-center gap-1 text-[10px] text-muted-foreground mt-2">
        <span class="mr-1">{{ total.toLocaleString() }} in the last year</span>
        <span class="ml-auto">Less</span>
        <span v-for="l in 5" :key="l" class="size-[11px] rounded-[2px]" :class="SCHEMES[scheme][l - 1]" />
        <span>More</span>
      </div>
    </div>
    <div v-else class="h-[120px] bg-muted/40 rounded animate-pulse" />
  </div>
</template>
