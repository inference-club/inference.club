<script setup lang="ts">
// Public profile page — JSON dump for PR 1. Real UI lands in PR 3.
// See docs/plans/service-manifest.md.

const route = useRoute()
const config = useRuntimeConfig()

const username = computed(() => String(route.params.username || ''))

const { data, error, pending } = await useFetch<unknown>(
  () => `${config.public.apiBase}/api/users/${encodeURIComponent(username.value)}/`,
  {
    credentials: 'include',
    // Surface 4xx as a normal error rather than throwing during SSR.
    onResponseError({ response }) {
      if (response.status === 404) {
        throw createError({ statusCode: 404, statusMessage: 'User not found' })
      }
    },
  },
)

useHead({
  title: () => (data.value ? `@${username.value} — inference.club` : 'inference.club'),
})
</script>

<template>
  <main class="container mx-auto max-w-4xl px-4 py-12">
    <h1 class="text-2xl font-semibold mb-2">@{{ username }}</h1>
    <p class="text-sm text-muted-foreground mb-6">
      PR-1 stub — raw JSON from <code>GET /api/users/{{ username }}/</code>.
      Designed UI lands in PR 3.
    </p>

    <div v-if="pending" class="text-sm text-muted-foreground">loading…</div>

    <div v-else-if="error" class="rounded border border-destructive/40 p-4">
      <p class="font-medium">Error</p>
      <pre class="text-xs mt-2 whitespace-pre-wrap">{{ error.message || error }}</pre>
    </div>

    <pre
      v-else
      class="rounded bg-muted/40 p-4 text-xs overflow-auto"
    >{{ JSON.stringify(data, null, 2) }}</pre>
  </main>
</template>
