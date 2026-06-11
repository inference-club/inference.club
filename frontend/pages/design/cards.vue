<script setup lang="ts">
import { fixtureRequests, stateRequests, worstCaseRequests } from '@/utils/designFixtures'
import { tracksFromRequests } from '@/utils/player'

definePageMeta({ layout: 'app', middleware: 'staff' })

const types = Object.keys(fixtureRequests)

// Track rows (PRD 06): the playlist row component with a normal title, a
// cover, and a worst-case unbroken-token title.
const trackFixtures = tracksFromRequests([
  fixtureRequests.MUSIC,
  ...worstCaseRequests.filter((r) => r.inference_type === 'MUSIC'),
])
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-4 sm:px-6 py-6">
    <h1 class="text-2xl font-semibold tracking-tight">Inference request cards</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Fixture-driven — no API calls. Cards are display-only (<code class="text-xs">linkable=false</code>).
    </p>

    <section v-for="t in types" :key="t" class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">{{ t }}</h2>
      <InferenceRequestCard :request="fixtureRequests[t]" :linkable="false" :actions="false" />
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">
        With owner action bar
      </h2>
      <InferenceRequestCard :request="fixtureRequests.IMAGE" :linkable="false" :actions="true" />
    </section>

    <section v-if="trackFixtures.length" class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">
        Playlist track rows
      </h2>
      <p class="mb-2 text-xs text-muted-foreground">
        The Spotify-style row used on playlists and the music home, including a
        worst-case unbroken title. Clicking plays through the global player bar.
      </p>
      <TrackList :tracks="trackFixtures" />
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">
        Abnormal states
      </h2>
      <div class="grid gap-4">
        <InferenceRequestCard
          v-for="r in stateRequests"
          :key="r.id"
          :request="r"
          :linkable="false"
          :actions="false"
        />
      </div>
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">
        Worst-case overflow fixtures
      </h2>
      <p class="mb-2 text-xs text-muted-foreground">
        Unbroken 120-char tokens, marathon URLs, max-length model names. If these don't
        cause horizontal scroll on the mobile shot, real content won't either.
      </p>
      <div class="grid gap-4">
        <InferenceRequestCard
          v-for="r in worstCaseRequests"
          :key="r.id"
          :request="r"
          :linkable="false"
          :actions="false"
        />
      </div>
    </section>
  </div>
</template>
