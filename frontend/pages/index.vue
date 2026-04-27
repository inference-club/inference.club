<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ArrowRight, Cpu, Network, Send, Lock, Code2, Users } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import CodeBlock from '@/components/CodeBlock.vue'

const { isAuthenticated } = useAuth()

const consumerSnippet = `# 1. Get a key at inference.club/dashboard/settings/token
export OPENAI_API_KEY=ic_xxxxxxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=https://api.inference.club/v1

# 2. Use any OpenAI-compatible client. That's it.
curl $OPENAI_BASE_URL/chat/completions \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "qwen3-30b-a3b",
    "messages": [
      {"role": "user", "content": "explain MoE in one sentence"}
    ]
  }'`

const providerSnippet = `# Already running vLLM / llama.cpp / Ollama on your GPU?
# Point the agent at it and join the network.
export INFERENCE_CLUB_API_KEY=ic_xxxxxxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=local-key  # whatever your local server expects

docker run --rm -d --name club-agent \\
  --network host \\
  -e INFERENCE_CLUB_API_KEY \\
  -e OPENAI_BASE_URL \\
  -e OPENAI_API_KEY \\
  ghcr.io/inference-club/inference-club-agent:latest

# The agent joins the inference.club tailnet, advertises the models
# your local server is serving, and starts taking requests.`

const features = [
  {
    icon: Code2,
    title: 'Drop-in OpenAI compatible',
    body: 'Same SDKs, same request/response shape. Just swap the base URL and key.',
  },
  {
    icon: Cpu,
    title: 'Real models from real GPUs',
    body: 'Members run open-weight models on their own hardware — Qwen, Llama, DeepSeek, whatever they like.',
  },
  {
    icon: Lock,
    title: 'Private by default',
    body: 'Requests reach providers over a private Tailscale network. No public endpoints to scrape, no third party in the path.',
  },
  {
    icon: Users,
    title: 'A club, not a vendor',
    body: 'Pool compute with people you trust. Bring a node when you have spare cycles, use the network when you need them.',
  },
]
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="relative px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-24 sm:pb-16">
      <div class="max-w-5xl mx-auto text-center">
        <h1 class="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight">
          A distributed inference network<br>
          powered by <span class="text-primary">consumer GPUs</span>
          and <span class="text-primary">Tailscale</span>
        </h1>
        <p class="mt-6 text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto">
          inference.club is an OpenAI-compatible API backed by GPUs that members bring to the network.
          Run an agent on your own hardware, and use the whole pool through one endpoint.
        </p>
        <div class="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <template v-if="isAuthenticated">
            <NuxtLink to="/dashboard">
              <Button size="lg" class="w-full sm:w-auto">
                Go to Dashboard
                <ArrowRight class="ml-2 h-4 w-4" />
              </Button>
            </NuxtLink>
          </template>
          <template v-else>
            <NuxtLink to="/sign-up">
              <Button size="lg" class="w-full sm:w-auto">
                Get an API key
                <ArrowRight class="ml-2 h-4 w-4" />
              </Button>
            </NuxtLink>
            <NuxtLink to="/docs/providers/run-an-agent">
              <Button size="lg" variant="outline" class="w-full sm:w-auto">
                Run an agent
              </Button>
            </NuxtLink>
          </template>
        </div>
      </div>
    </section>

    <!-- Two-side code samples -->
    <section class="px-4 sm:px-6 lg:px-8 pb-16">
      <div class="max-w-6xl mx-auto">
        <div class="grid lg:grid-cols-2 gap-6">
          <!-- Consumer -->
          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <Send class="h-4 w-4 text-primary" />
              <h2 class="text-sm font-semibold uppercase tracking-wide">Use the network</h2>
            </div>
            <h3 class="text-2xl font-bold">Drop-in for the OpenAI SDK</h3>
            <p class="text-muted-foreground text-sm">
              Sign up, mint a token, point your client at <code class="font-mono text-foreground">api.inference.club/v1</code>.
            </p>
            <CodeBlock :code="consumerSnippet" label="consumer.sh" lang="bash" />
          </div>

          <!-- Provider -->
          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <Cpu class="h-4 w-4 text-primary" />
              <h2 class="text-sm font-semibold uppercase tracking-wide">Bring a node</h2>
            </div>
            <h3 class="text-2xl font-bold">Wrap any OpenAI-compatible server</h3>
            <p class="text-muted-foreground text-sm">
              Run the agent next to vLLM, llama.cpp, Ollama, or any
              <code class="font-mono text-foreground">/v1</code>-shaped server you already have.
            </p>
            <CodeBlock :code="providerSnippet" label="provider.sh" lang="bash" />
          </div>
        </div>
      </div>
    </section>

    <!-- How it works -->
    <section class="px-4 sm:px-6 lg:px-8 py-16 bg-muted/40 border-y">
      <div class="max-w-5xl mx-auto">
        <h2 class="text-3xl font-bold text-center mb-2">How it works</h2>
        <p class="text-center text-muted-foreground mb-12">
          Three pieces. Nothing magic.
        </p>
        <div class="grid md:grid-cols-3 gap-6">
          <Card class="p-6">
            <div class="flex items-center gap-3 mb-3">
              <div class="h-8 w-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-mono text-sm">1</div>
              <Cpu class="h-5 w-5 text-muted-foreground" />
            </div>
            <h3 class="font-semibold mb-1">Operators run agents</h3>
            <p class="text-sm text-muted-foreground">
              Members run <code class="font-mono">inference-club-agent</code> on a GPU box,
              pointing it at their local LLM server.
            </p>
          </Card>
          <Card class="p-6">
            <div class="flex items-center gap-3 mb-3">
              <div class="h-8 w-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-mono text-sm">2</div>
              <Network class="h-5 w-5 text-muted-foreground" />
            </div>
            <h3 class="font-semibold mb-1">Agents join the tailnet</h3>
            <p class="text-sm text-muted-foreground">
              Each agent gets a short-lived Tailscale key, joins our private
              network, and registers the models it serves.
            </p>
          </Card>
          <Card class="p-6">
            <div class="flex items-center gap-3 mb-3">
              <div class="h-8 w-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-mono text-sm">3</div>
              <Send class="h-5 w-5 text-muted-foreground" />
            </div>
            <h3 class="font-semibold mb-1">Consumers send requests</h3>
            <p class="text-sm text-muted-foreground">
              Calls to <code class="font-mono">api.inference.club</code> route to
              an online agent serving the requested model. Streaming works.
            </p>
          </Card>
        </div>
      </div>
    </section>

    <!-- Why -->
    <section class="px-4 sm:px-6 lg:px-8 py-16">
      <div class="max-w-5xl mx-auto">
        <h2 class="text-3xl font-bold text-center mb-12">Why inference.club</h2>
        <div class="grid sm:grid-cols-2 gap-6">
          <Card v-for="f in features" :key="f.title" class="p-6">
            <CardContent class="p-0">
              <component :is="f.icon" class="h-6 w-6 text-primary mb-3" />
              <h3 class="font-semibold mb-1">{{ f.title }}</h3>
              <p class="text-sm text-muted-foreground">{{ f.body }}</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="px-4 sm:px-6 lg:px-8 py-20 border-t">
      <div class="max-w-3xl mx-auto text-center">
        <h2 class="text-3xl font-bold mb-4">Ready to plug in?</h2>
        <p class="text-muted-foreground mb-8">
          Sign in with GitHub, mint a key, and you're live in about a minute.
        </p>
        <div class="flex flex-col sm:flex-row gap-3 justify-center">
          <NuxtLink :to="isAuthenticated ? '/dashboard' : '/sign-up'">
            <Button size="lg" class="w-full sm:w-auto">
              {{ isAuthenticated ? 'Go to Dashboard' : 'Get an API key' }}
              <ArrowRight class="ml-2 h-4 w-4" />
            </Button>
          </NuxtLink>
          <NuxtLink to="/docs">
            <Button size="lg" variant="outline" class="w-full sm:w-auto">
              Read the docs
            </Button>
          </NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>
