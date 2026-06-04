<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { dashboardNav } from '@/composables/useDashboardNav'

const route = useRoute()
const { t, locale, defaultLocale } = useI18n()

const humanize = (seg: string) =>
  seg.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

// nav urls are locale-free; strip the /<locale> prefix that
// prefix_except_default adds so matching against them works in every locale.
const stripLocale = (path: string): string => {
  if (locale.value === defaultLocale) return path
  const prefix = `/${locale.value}`
  if (path === prefix) return '/'
  return path.startsWith(`${prefix}/`) ? path.slice(prefix.length) : path
}

// Humanized path segments after /dashboard — the universal fallback so the
// breadcrumb is never empty even if the nav config is momentarily unavailable.
const fallbackCrumbs = (path: string): string[] => {
  const segs = path.split('/').filter(Boolean)
  const after = segs[0] === 'dashboard' ? segs.slice(1) : segs
  return after.length ? after.map(humanize) : [t('dashboard.home')]
}

const crumbs = computed<string[]>(() => {
  const path = stripLocale(route.path.replace(/\/+$/, '') || '/')

  if (path === '/dashboard') return [t('dashboard.home')]

  // Request detail is reachable from both "Your" and "All", so attribute it to
  // the group rather than a specific sidebar item.
  const detail = path.match(/^\/dashboard\/inference\/requests\/(\d+)$/)
  if (detail) return [t('dashboard.groups.inferenceRequests'), t('dashboard.requestDetail', { id: detail[1] })]

  // Guard the nav lookup so a transiently-undefined import can never throw and
  // wipe the breadcrumb — we just fall back to humanized path segments.
  const nav = Array.isArray(dashboardNav) ? dashboardNav : []

  // Exact sidebar item match → [group, item].
  for (const group of nav) {
    for (const item of group.items) {
      if (item.url === path) return [t(group.titleKey), t(item.titleKey)]
    }
  }

  // Deepest prefix match for nested pages under a sidebar item.
  let best: { group: string; item: string; url: string } | null = null
  for (const group of nav) {
    for (const item of group.items) {
      if (path.startsWith(item.url + '/') && (!best || item.url.length > best.url.length)) {
        best = { group: t(group.titleKey), item: t(item.titleKey), url: item.url }
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
