<script setup lang="ts">
import { fixtureRequests, worstCaseRequests } from '@/utils/designFixtures'

definePageMeta({ layout: 'app', middleware: 'staff' })

const types = Object.keys(fixtureRequests)
</script>

<template>
  <div class="mx-auto max-w-3xl p-6">
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
