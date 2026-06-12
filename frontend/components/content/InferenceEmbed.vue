<script setup lang="ts">
// MDC embed of a real inference request inside a blog post. Usage:
//   ::inference-embed{:id="1234" caption="LTX-2 on the DGX Spark, 9s clip"}
//   ::
//
// The detail endpoint (/api/inference/requests/<id>/) currently requires
// authentication, so anonymous readers get the fallback card: the caption,
// a short explanation, and a link to the live request. Logged-in readers
// (and previews) get the full InferenceRequestCard. When a public
// single-request endpoint ships (PRD 08 territory), this component starts
// working for everyone with no markup changes.
import { ref, onMounted } from 'vue'
import { ExternalLink, Activity } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'

const props = defineProps<{
  id: number | string
  caption?: string
}>()

const config = useRuntimeConfig()
const request = ref<InferenceRequest | null>(null)
const failed = ref(false)

const requestUrl = `/dashboard/inference/requests?focus=${props.id}`

onMounted(async () => {
  try {
    const res = await fetch(
      `${config.public.apiBase}/api/inference/requests/${props.id}/`,
      { credentials: 'include' },
    )
    if (!res.ok) throw new Error(String(res.status))
    request.value = await res.json()
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <figure class="not-prose my-8">
    <InferenceRequestCard
      v-if="request"
      :request="request"
      :linkable="false"
      :actions="false"
      show-owner
    />
    <div
      v-else
      class="rounded-lg border bg-muted/30 px-4 py-5 text-sm text-muted-foreground"
    >
      <p class="flex items-center gap-2 font-medium text-foreground">
        <Activity class="size-4 text-sky-500" />
        Inference request #{{ id }}
      </p>
      <p class="mt-1.5">
        <template v-if="failed">
          This embed shows a live generation from the inference.club network —
          sign in to see it inline, or
          <NuxtLink :to="requestUrl" class="underline underline-offset-4 inline-flex items-center gap-1">
            view it on the platform <ExternalLink class="size-3" />
          </NuxtLink>.
        </template>
        <template v-else>Loading…</template>
      </p>
    </div>
    <figcaption v-if="caption" class="mt-2 text-center text-xs text-muted-foreground">
      {{ caption }}
    </figcaption>
  </figure>
</template>
