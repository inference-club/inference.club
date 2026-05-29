<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { dashboardNav } from '@/composables/useDashboardNav'

const route = useRoute()

const humanize = (seg: string) =>
  seg.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

// Build the breadcrumb trail from the current route, lined up with the sidebar
// nav. Plain text (not links) — they just mirror where you are.
// Humanized path segments after /dashboard — the universal fallback so the
// breadcrumb is never empty even if the nav config is momentarily unavailable.
const fallbackCrumbs = (path: string): string[] => {
  const segs = path.split('/').filter(Boolean)
  const after = segs[0] === 'dashboard' ? segs.slice(1) : segs
  return after.length ? after.map(humanize) : ['Dashboard']
}

const crumbs = computed<string[]>(() => {
  const path = route.path.replace(/\/+$/, '') || '/'

  if (path === '/dashboard') return ['Dashboard']

  // Request detail is reachable from both "Your" and "All", so attribute it to
  // the group rather than a specific sidebar item.
  const detail = path.match(/^\/dashboard\/inference\/requests\/(\d+)$/)
  if (detail) return ['Inference Requests', `Request #${detail[1]}`]

  // Guard the nav lookup so a transiently-undefined import can never throw and
  // wipe the breadcrumb — we just fall back to humanized path segments.
  const nav = Array.isArray(dashboardNav) ? dashboardNav : []

  // Exact sidebar item match → [group, item].
  for (const group of nav) {
    for (const item of group.items) {
      if (item.url === path) return [group.title, item.title]
    }
  }

  // Deepest prefix match for nested pages under a sidebar item.
  let best: { group: string; item: string; url: string } | null = null
  for (const group of nav) {
    for (const item of group.items) {
      if (path.startsWith(item.url + '/') && (!best || item.url.length > best.url.length)) {
        best = { group: group.title, item: item.title, url: item.url }
      }
    }
  }
  if (best) {
    const leaf = humanize(path.slice(best.url.length + 1).split('/')[0])
    return [best.group, best.item, leaf]
  }

  return fallbackCrumbs(path)
})
</script>

<template>
  <Breadcrumb>
    <BreadcrumbList>
      <template v-for="(crumb, i) in crumbs" :key="i">
        <BreadcrumbItem :class="i < crumbs.length - 1 ? 'hidden md:block' : ''">
          <BreadcrumbPage v-if="i === crumbs.length - 1">{{ crumb }}</BreadcrumbPage>
          <span v-else class="text-muted-foreground">{{ crumb }}</span>
        </BreadcrumbItem>
        <BreadcrumbSeparator v-if="i < crumbs.length - 1" class="hidden md:block" />
      </template>
    </BreadcrumbList>
  </Breadcrumb>
</template>
