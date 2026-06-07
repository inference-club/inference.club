<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Users, UserPlus, Activity, Coins, Cpu, Radio, ShieldAlert, Boxes,
} from 'lucide-vue-next'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useAdmin, type AdminActivity } from '@/composables/useAdmin'

definePageMeta({
  layout: 'app',
  middleware: 'staff',
})

const { getActivity, loading, error } = useAdmin()
const data = ref<AdminActivity | null>(null)

const load = async () => {
  try {
    data.value = await getActivity()
  } catch {
    // surfaced via `error`
  }
}
onMounted(load)

const nf = new Intl.NumberFormat()
const fmt = (n: number | null | undefined) => nf.format(n ?? 0)

const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })
const fmtCompact = (n: number | null | undefined) => compact.format(n ?? 0)

// Peak request count over the 14-day window, for bar heights.
const peakDaily = computed(() =>
  Math.max(1, ...(data.value?.daily ?? []).map(d => d.requests)),
)

const fmtJoined = (iso: string) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch {
    return iso
  }
}

const fmtDay = (iso: string) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="container mx-auto p-6 space-y-6 max-w-5xl">
    <div>
      <h1 class="text-2xl font-bold">Activity</h1>
      <p class="text-muted-foreground text-sm mt-1">
        A staff snapshot of members, inference traffic, the live node network,
        and the moderation backlog.
      </p>
    </div>

    <div v-if="loading && !data" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card v-for="i in 8" :key="i" class="p-4 h-24 animate-pulse" />
    </div>

    <div v-else-if="error" class="text-destructive text-sm py-8 text-center">
      {{ error }}
    </div>

    <template v-else-if="data">
      <!-- Members -->
      <section class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Members</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Users class="size-4" /> Total members
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.users.total) }}</div>
            <div class="text-xs text-muted-foreground mt-1">{{ fmt(data.users.staff) }} staff</div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <UserPlus class="size-4" /> New (24h)
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.users.new_24h) }}</div>
            <div class="text-xs text-muted-foreground mt-1">{{ fmt(data.users.new_7d) }} this week</div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Activity class="size-4" /> Active (24h)
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.users.active_24h) }}</div>
            <div class="text-xs text-muted-foreground mt-1">made ≥1 request</div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <UserPlus class="size-4" /> New (30d)
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.users.new_30d) }}</div>
          </Card>
        </div>
      </section>

      <!-- Inference -->
      <section class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Inference</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Activity class="size-4" /> Requests (total)
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.requests.total) }}</div>
            <div class="text-xs text-muted-foreground mt-1">
              {{ fmt(data.requests.last_24h) }} in 24h · {{ fmt(data.requests.last_7d) }} in 7d
            </div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Coins class="size-4" /> Tokens (total)
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmtCompact(data.tokens.total) }}</div>
            <div class="text-xs text-muted-foreground mt-1">
              {{ fmtCompact(data.tokens.last_24h) }} in 24h · {{ fmtCompact(data.tokens.last_7d) }} in 7d
            </div>
          </Card>
          <Card class="p-4 sm:col-span-2">
            <div class="text-muted-foreground text-xs mb-2">Requests by type</div>
            <div v-if="data.requests.by_type.length" class="flex flex-wrap gap-2">
              <Badge
                v-for="row in data.requests.by_type"
                :key="row.type"
                variant="secondary"
              >
                {{ row.type }} · {{ fmt(row.count) }}
              </Badge>
            </div>
            <div v-else class="text-xs text-muted-foreground">No requests yet.</div>
          </Card>
        </div>

        <!-- 14-day request sparkline -->
        <Card class="p-4">
          <div class="text-muted-foreground text-xs mb-3">Requests — last 14 days</div>
          <div class="flex items-end gap-1 h-24">
            <div
              v-for="d in data.daily"
              :key="d.date"
              class="flex-1 bg-primary/70 rounded-t hover:bg-primary transition-colors"
              :style="{ height: `${Math.max(2, (d.requests / peakDaily) * 100)}%` }"
              :title="`${fmtDay(d.date)}: ${fmt(d.requests)} requests, ${fmt(d.tokens)} tokens`"
            />
          </div>
          <div class="flex justify-between text-[10px] text-muted-foreground mt-2">
            <span>{{ data.daily.length ? fmtDay(data.daily[0].date) : '' }}</span>
            <span>{{ data.daily.length ? fmtDay(data.daily[data.daily.length - 1].date) : '' }}</span>
          </div>
        </Card>
      </section>

      <!-- Network -->
      <section class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Network</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Radio class="size-4" /> Nodes online
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.network.providers_online) }}</div>
            <div class="text-xs text-muted-foreground mt-1">
              {{ fmt(data.network.providers_active) }} active · {{ fmt(data.network.providers_total) }} total
            </div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Cpu class="size-4" /> Services
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.network.services_active) }}</div>
            <div class="text-xs text-muted-foreground mt-1">active services</div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Boxes class="size-4" /> Deployments
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.network.deployments_active) }}</div>
            <div class="text-xs text-muted-foreground mt-1">active model deployments</div>
          </Card>
          <Card class="p-4">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <Boxes class="size-4" /> Distinct models
            </div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.network.models_distinct) }}</div>
            <div class="text-xs text-muted-foreground mt-1">in the catalog</div>
          </Card>
        </div>
      </section>

      <!-- Moderation -->
      <section class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Moderation</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card class="p-4" :class="data.moderation.open > 0 ? 'border-destructive/50' : ''">
            <div class="flex items-center gap-2 text-muted-foreground text-xs">
              <ShieldAlert class="size-4" /> Open reports
            </div>
            <div
              class="text-2xl font-bold mt-1 tabular-nums"
              :class="data.moderation.open > 0 ? 'text-destructive' : ''"
            >
              {{ fmt(data.moderation.open) }}
            </div>
            <NuxtLink
              v-if="data.moderation.open > 0"
              to="/dashboard/admin/moderation"
              class="text-xs text-primary hover:underline mt-1 inline-block"
            >
              Review queue →
            </NuxtLink>
          </Card>
          <Card class="p-4">
            <div class="text-muted-foreground text-xs">Resolved</div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.moderation.resolved) }}</div>
          </Card>
          <Card class="p-4">
            <div class="text-muted-foreground text-xs">Dismissed</div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.moderation.dismissed) }}</div>
          </Card>
          <Card class="p-4">
            <div class="text-muted-foreground text-xs">Total reports</div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ fmt(data.moderation.total) }}</div>
          </Card>
        </div>
      </section>

      <!-- Recent signups -->
      <section class="space-y-3">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Recent signups</h2>
        <Card class="divide-y">
          <div
            v-for="u in data.recent_signups"
            :key="u.owner + u.joined"
            class="flex items-center justify-between gap-4 px-4 py-2.5 text-sm"
          >
            <div class="flex items-center gap-2 min-w-0">
              <component
                :is="u.github_login ? 'a' : 'span'"
                v-bind="u.github_login ? { href: `https://github.com/${u.github_login}`, target: '_blank', rel: 'noopener' } : {}"
                class="font-medium truncate"
                :class="u.github_login ? 'hover:underline' : ''"
              >
                {{ u.owner }}
              </component>
              <Badge v-if="u.is_staff" variant="secondary" class="h-4 px-1 text-[10px]">Staff</Badge>
            </div>
            <span class="text-muted-foreground shrink-0">{{ fmtJoined(u.joined) }}</span>
          </div>
          <div v-if="!data.recent_signups.length" class="px-4 py-3 text-sm text-muted-foreground">
            No members yet.
          </div>
        </Card>
      </section>

      <p class="text-[10px] text-muted-foreground">
        Generated {{ new Date(data.generated_at).toLocaleString() }}
      </p>
    </template>
  </div>
</template>
