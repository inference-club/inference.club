<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Play, Shuffle, Music } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import type { Collection } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import { usePlayerStore } from '@/stores/player'
import { tracksFromRequests, formatRuntime } from '@/utils/player'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

const route = useRoute()
const username = computed(() => String(route.params.username || ''))
const slug = computed(() => String(route.params.slug || ''))
const { getPublicCollection } = useContentSharing()
const player = usePlayerStore()

const collection = ref<Collection | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

// Public playlists play too — the global player bar mounts in this layout.
const tracks = computed(() => tracksFromRequests(collection.value?.items ?? []))
const runtime = computed(() =>
  formatRuntime(tracks.value.reduce((s, tr) => s + (tr.duration ?? 0), 0)),
)
const playAll = () => player.playQueue(tracks.value, 0)
const shuffleAll = () => player.playQueue(tracks.value, -1, { shuffle: true })

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collection.value = await getPublicCollection(username.value, slug.value)
  } catch {
    error.value = 'Collection not found or not public.'
  } finally {
    loading.value = false
  }
}

useHead(() => ({
  title: collection.value
    ? `${collection.value.name} · @${username.value}`
    : 'Collection',
}))

onMounted(load)
</script>

<template>
  <div class="container mx-auto py-8 max-w-5xl px-4">
    <NuxtLink
      :to="`/${username}`"
      class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
    >
      <ArrowLeft class="size-4" /> @{{ username }}
    </NuxtLink>

    <div v-if="loading" class="space-y-4">
      <div class="h-8 w-64 bg-muted rounded animate-pulse" />
      <Card class="p-4 animate-pulse h-40" />
    </div>

    <div v-else-if="error" class="text-center py-16 text-muted-foreground">{{ error }}</div>

    <template v-else-if="collection">
      <div class="mb-6 flex items-start gap-4">
        <div v-if="collection.cover_image_url || tracks.length" class="size-24 shrink-0 sm:size-28">
          <img
            v-if="collection.cover_image_url"
            :src="collection.cover_image_url"
            class="size-full rounded-xl border object-cover shadow-sm"
            :alt="collection.name"
          />
          <div v-else class="flex size-full items-center justify-center rounded-xl border bg-muted">
            <Music class="size-8 text-muted-foreground" />
          </div>
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-2xl font-bold break-words">{{ collection.name }}</h1>
            <VisibilityBadge :visibility="collection.visibility" />
          </div>
          <p v-if="collection.description" class="text-muted-foreground mt-1 break-words">
            {{ collection.description }}
          </p>
          <p class="text-sm text-muted-foreground mt-1">
            by
            <NuxtLink :to="`/${collection.github_login || username}`" class="underline font-mono">
              @{{ collection.github_login || username }}
            </NuxtLink>
            · {{ collection.item_count }} item{{ collection.item_count === 1 ? '' : 's' }}
            <template v-if="runtime"> · {{ runtime }}</template>
          </p>
          <div v-if="tracks.length" class="mt-3 flex items-center gap-2">
            <Button class="gap-2 rounded-full" @click="playAll">
              <Play class="size-4" /> Play
            </Button>
            <Button v-if="tracks.length > 1" variant="outline" class="gap-2 rounded-full" @click="shuffleAll">
              <Shuffle class="size-4" /> Shuffle
            </Button>
          </div>
        </div>
      </div>

      <div
        v-if="!collection.items?.length"
        class="text-center py-12 text-muted-foreground"
      >
        Nothing public in this collection yet.
      </div>

      <div v-else class="space-y-4">
        <InferenceRequestCard
          v-for="request in collection.items"
          :key="request.id"
          :request="request"
          :linkable="false"
          :actions="false"
          show-owner
        />
      </div>
    </template>
  </div>
</template>
