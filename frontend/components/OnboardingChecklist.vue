<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Check, KeyRound, Server, Send, Copy, Rocket } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/composables/useAuth'
import { useProviders } from '@/composables/useProviders'
import { useInferenceRequest } from '@/composables/useInferenceRequest'

const { user } = useAuth()
const config = useRuntimeConfig()
const { providers, fetchProviders } = useProviders()
const { listInferenceRequests } = useInferenceRequest()

const requestCount = ref<number | null>(null)
const loaded = ref(false)

onMounted(async () => {
  await Promise.all([
    fetchProviders(),
    listInferenceRequests(1, 0)
      .then((res) => { requestCount.value = res.count })
      .catch(() => { requestCount.value = 0 }),
  ])
  loaded.value = true
})

const activeModels = computed(() => {
  const names = new Set<string>()
  for (const p of providers.value)
    for (const m of p.models) if (m.is_active) names.add(m.name)
  return Array.from(names)
})
const hasNodeWithModel = computed(() => activeModels.value.length > 0)
const hasRequested = computed(() => (requestCount.value ?? 0) > 0)
const firstModel = computed(() => activeModels.value[0] ?? 'MODEL_NAME')

// Hide once the user has both registered a model-serving node and made a request.
const allDone = computed(() => hasNodeWithModel.value && hasRequested.value)

const apiKey = computed(() => user.value?.api_token ?? 'YOUR_API_KEY')
const curlSnippet = computed(
  () => `curl ${config.public.apiBase}/v1/chat/completions \\
  -H "Authorization: Bearer ${apiKey.value}" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "${firstModel.value}", "messages": [{"role": "user", "content": "Hello!"}]}'`,
)

const showCurl = ref(false)
const copied = ref('')
const copy = async (text: string, what: string) => {
  await navigator.clipboard.writeText(text)
  copied.value = what
  setTimeout(() => { if (copied.value === what) copied.value = '' }, 2000)
}
</script>

<template>
  <Card v-if="loaded && !allDone" class="p-6 border-primary/30 bg-primary/[0.03]">
    <div class="flex items-start gap-2 mb-5">
      <Rocket class="h-5 w-5 text-primary mt-0.5 shrink-0" />
      <div>
        <h2 class="text-lg font-semibold leading-tight">Get started</h2>
        <p class="text-sm text-muted-foreground">
          A couple of steps and you're live on the network.
        </p>
      </div>
    </div>

    <ol class="space-y-4">
      <!-- Step 1: API key (auto-minted, always done) -->
      <li class="flex gap-3">
        <span class="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check class="size-3.5" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="font-medium flex items-center gap-1.5">
            <KeyRound class="size-4 text-muted-foreground" /> Your API key is ready
          </p>
          <p class="text-sm text-muted-foreground mb-2">
            Auto-created for your account — use it with any OpenAI-compatible client.
          </p>
          <div class="flex items-center gap-2">
            <code class="flex-1 min-w-0 truncate px-2 py-1 rounded bg-muted font-mono text-xs">{{ apiKey }}</code>
            <Button variant="outline" size="sm" class="shrink-0" @click="copy(apiKey, 'key')">
              <Copy class="size-3.5" /> {{ copied === 'key' ? 'Copied!' : 'Copy' }}
            </Button>
          </div>
        </div>
      </li>

      <!-- Step 2: Register a node with a model -->
      <li class="flex gap-3">
        <span
          class="flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
          :class="hasNodeWithModel ? 'bg-primary text-primary-foreground' : 'border border-muted-foreground/40 text-muted-foreground'"
        >
          <Check v-if="hasNodeWithModel" class="size-3.5" />
          <template v-else>2</template>
        </span>
        <div class="min-w-0 flex-1">
          <p class="font-medium flex items-center gap-1.5">
            <Server class="size-4 text-muted-foreground" /> Register a node with a model
          </p>
          <template v-if="hasNodeWithModel">
            <p class="text-sm text-muted-foreground">
              Serving {{ activeModels.length }} model{{ activeModels.length === 1 ? '' : 's' }}:
              <span class="font-mono text-foreground">{{ activeModels.slice(0, 3).join(', ') }}</span>
            </p>
          </template>
          <template v-else>
            <p class="text-sm text-muted-foreground mb-2">
              Run the agent on a machine with an LLM server. It joins the tailnet
              and registers automatically — no node here yet.
            </p>
            <Button as-child size="sm">
              <NuxtLink to="/docs/providers/run-an-agent">
                Run an agent
              </NuxtLink>
            </Button>
          </template>
        </div>
      </li>

      <!-- Step 3: Make your first request -->
      <li class="flex gap-3">
        <span
          class="flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
          :class="hasRequested ? 'bg-primary text-primary-foreground' : 'border border-muted-foreground/40 text-muted-foreground'"
        >
          <Check v-if="hasRequested" class="size-3.5" />
          <template v-else>3</template>
        </span>
        <div class="min-w-0 flex-1">
          <p class="font-medium flex items-center gap-1.5">
            <Send class="size-4 text-muted-foreground" /> Make your first request
          </p>
          <template v-if="hasRequested">
            <p class="text-sm text-muted-foreground">
              Nice — you've sent {{ requestCount }} request{{ requestCount === 1 ? '' : 's' }}.
            </p>
          </template>
          <template v-else>
            <p class="text-sm text-muted-foreground mb-2">
              Try any accessible model right here, or call the API with your key.
            </p>
            <div class="flex flex-wrap items-center gap-2">
              <Button as-child size="sm">
                <NuxtLink to="/dashboard/playground">
                  Open playground
                </NuxtLink>
              </Button>
              <Button variant="outline" size="sm" @click="showCurl = !showCurl">
                {{ showCurl ? 'Hide' : 'Show' }} curl example
              </Button>
            </div>
            <div v-if="showCurl" class="mt-3">
              <div class="relative">
                <pre class="overflow-x-auto rounded bg-muted p-3 text-xs font-mono"><code>{{ curlSnippet }}</code></pre>
                <Button
                  variant="outline"
                  size="sm"
                  class="absolute top-2 right-2"
                  @click="copy(curlSnippet, 'curl')"
                >
                  <Copy class="size-3.5" /> {{ copied === 'curl' ? 'Copied!' : 'Copy' }}
                </Button>
              </div>
              <p v-if="!hasNodeWithModel" class="text-xs text-muted-foreground mt-1.5">
                Replace <code class="font-mono">MODEL_NAME</code> once a node is serving a model.
              </p>
            </div>
          </template>
        </div>
      </li>
    </ol>
  </Card>
</template>
