<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Button } from '@/components/ui/button'
import { ArrowRight, Cpu, Network, Send, Lock, Code2, Users, Zap, Server } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import { useProviders } from '@/composables/useProviders'
import CodeTabs from '@/components/CodeTabs.vue'

const { t, locale } = useI18n()
const localePath = useLocalePath()
const { isAuthenticated } = useAuth()

// Nudge signed-in members who haven't put a model-serving node on the network yet.
const { providers, fetchProviders } = useProviders()
const nodesChecked = ref(false)
onMounted(async () => {
  if (!isAuthenticated.value) return
  await fetchProviders()
  nodesChecked.value = true
})
const needsNode = computed(
  () =>
    isAuthenticated.value &&
    nodesChecked.value &&
    !providers.value.some(p => p.models.some(m => m.is_active)),
)

// Featured blog post for the homepage: the newest post flagged `featured`,
// else the newest post overall — in the active locale, falling back to English.
const { listMerged } = useLocalizedContent()
const { data: featuredPost } = await useAsyncData(
  'home:featured',
  async () => {
    const posts = await listMerged('blog', q => q.order('publishedAt', 'DESC'))
    return posts.find(p => p.featured) ?? posts[0] ?? null
  },
  { watch: [locale] },
)

const consumerSnippets = [
  {
    label: 'curl',
    lang: 'bash',
    code: `export OPENAI_API_KEY=ic_xxxxxxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=https://api.inference.club/v1

curl $OPENAI_BASE_URL/chat/completions \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "qwen/qwen3.6-27b",
    "messages": [
      {"role": "user", "content": "explain MoE in one sentence"}
    ]
  }'`,
  },
  {
    label: 'Python',
    lang: 'python',
    code: `from openai import OpenAI

client = OpenAI(
    api_key="ic_xxxxxxxxxxxxxxxxxxxx",
    base_url="https://api.inference.club/v1",
)

resp = client.chat.completions.create(
    model="qwen/qwen3.6-27b",
    messages=[
        {"role": "user", "content": "explain MoE in one sentence"},
    ],
)
print(resp.choices[0].message.content)`,
  },
  {
    label: 'TypeScript',
    lang: 'typescript',
    code: `import OpenAI from "openai"

const client = new OpenAI({
  apiKey: process.env.INFERENCE_CLUB_KEY,
  baseURL: "https://api.inference.club/v1",
})

const resp = await client.chat.completions.create({
  model: "qwen/qwen3.6-27b",
  messages: [
    { role: "user", content: "explain MoE in one sentence" },
  ],
})

console.log(resp.choices[0].message.content)`,
  },
]

const providerSnippets = [
  {
    label: 'docker',
    lang: 'bash',
    code: `# Already running vLLM, llama.cpp, or Ollama on your GPU?
# Point the agent at it and join the network.

export INFERENCE_CLUB_API_KEY=ic_xxxxxxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=local-key  # whatever your local server expects

docker run --rm -d --name club-agent --network host \\
  -e INFERENCE_CLUB_API_KEY \\
  -e OPENAI_BASE_URL \\
  -e OPENAI_API_KEY \\
  ghcr.io/inference-club/inference-club-agent:latest`,
  },
  {
    label: 'binary',
    lang: 'bash',
    code: `# Or just run the static binary — no Docker required.

export INFERENCE_CLUB_API_KEY=ic_xxxxxxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=local-key

./inference-club-agent

# The agent registers, joins the inference.club tailnet,
# advertises the models your local server is serving,
# and starts taking requests. That's it.`,
  },
]

// Feature cards: visual config lives here; copy is resolved from i18n keys in
// the template so all four cards localize without duplicating strings.
const features = [
  { icon: Code2, key: 'feature1', grad: 'from-violet-500 to-fuchsia-500' },
  { icon: Cpu, key: 'feature2', grad: 'from-fuchsia-500 to-rose-500' },
  { icon: Lock, key: 'feature3', grad: 'from-cyan-500 to-violet-500' },
  { icon: Users, key: 'feature4', grad: 'from-emerald-500 to-cyan-500' },
]
</script>

<template>
  <div class="relative overflow-x-clip">
    <!-- Ambient background effects -->
    <div class="pointer-events-none absolute inset-0 -z-10">
      <div class="absolute inset-x-0 top-0 h-[800px] bg-[radial-gradient(ellipse_at_top,rgba(139,92,246,0.18),transparent_55%)]" />
      <div class="absolute -top-20 left-1/2 -translate-x-1/2 h-[500px] w-[900px] rounded-full blur-3xl opacity-50 bg-[radial-gradient(circle,rgba(217,70,239,0.25),transparent_60%)]" />
      <div
        class="absolute inset-0 opacity-[0.025] dark:opacity-[0.06]"
        :style="{
          backgroundImage: 'radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)',
          backgroundSize: '32px 32px',
        }"
      />
    </div>

    <!-- Hero -->
    <section class="relative px-4 sm:px-6 lg:px-8 pt-20 pb-16 sm:pt-28 sm:pb-20">
      <div class="max-w-5xl mx-auto text-center">
        <div class="inline-flex items-center gap-2 rounded-full border bg-background/60 backdrop-blur px-3 py-1 text-xs font-mono mb-8 shadow-sm">
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span class="text-muted-foreground">{{ t('home.liveAt') }}</span>
          <span class="text-foreground">api.inference.club</span>
        </div>

        <h1 class="text-5xl sm:text-6xl md:text-7xl font-bold tracking-tight leading-[1.05]">
          {{ t('home.heroTitleLead') }}
          <span class="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-cyan-500 bg-clip-text text-transparent">
            {{ t('home.heroConsumerGpus') }}
          </span>
          {{ t('home.heroAnd') }}
          <span class="bg-gradient-to-r from-cyan-500 via-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
            {{ t('home.heroTailscale') }}
          </span>
        </h1>

        <p class="mt-8 text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          {{ t('home.heroSubtitle') }}
        </p>

        <div class="mt-10 flex flex-col sm:flex-row gap-3 justify-center">
          <template v-if="isAuthenticated">
            <NuxtLink :to="localePath('/dashboard')">
              <Button size="lg" class="w-full sm:w-auto h-12 px-6 text-base">
                {{ t('home.goToDashboard') }}
                <ArrowRight class="ml-2 h-4 w-4" />
              </Button>
            </NuxtLink>
            <NuxtLink v-if="needsNode" :to="localePath('/docs/providers/run-an-agent')">
              <Button size="lg" variant="outline" class="w-full sm:w-auto h-12 px-6 text-base">
                {{ t('home.runAnAgent') }}
              </Button>
            </NuxtLink>
          </template>
          <template v-else>
            <NuxtLink :to="localePath('/login')">
              <Button size="lg" class="w-full sm:w-auto h-12 px-6 text-base shadow-lg shadow-violet-500/20">
                {{ t('home.getApiKey') }}
                <ArrowRight class="ml-2 h-4 w-4" />
              </Button>
            </NuxtLink>
            <NuxtLink :to="localePath('/docs/providers/run-an-agent')">
              <Button size="lg" variant="outline" class="w-full sm:w-auto h-12 px-6 text-base">
                {{ t('home.runAnAgent') }}
              </Button>
            </NuxtLink>
          </template>
        </div>

        <NuxtLink
          v-if="needsNode"
          :to="localePath('/dashboard')"
          class="mt-6 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/[0.06] px-4 py-1.5 text-sm text-foreground transition-colors hover:bg-primary/10"
        >
          <Server class="h-4 w-4 text-primary" />
          {{ t('home.needsNode') }}
          <ArrowRight class="h-3.5 w-3.5" />
        </NuxtLink>

      </div>
    </section>

    <!-- 3D network visualization (full-bleed) -->
    <section class="relative pb-20">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-8">
          <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">{{ t('home.topologyEyebrow') }}</p>
          <h2 class="text-3xl sm:text-4xl font-bold tracking-tight">
            {{ t('home.topologyTitleLead') }}
            <span class="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-cyan-500 bg-clip-text text-transparent">{{ t('home.topologyTitleHighlight') }}</span>.
          </h2>
          <p class="mt-5 text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            {{ t('home.topologySubtitle') }}
          </p>
        </div>
      </div>
      <div class="w-full h-[520px] sm:h-[620px] md:h-[720px] relative bg-[#f5f3ec] dark:bg-[#0a0d18] overflow-hidden border-y border-slate-200/50 dark:border-slate-800/50">
        <!-- Dotted grid pattern -->
        <div
          class="pointer-events-none absolute inset-0 opacity-[0.07] dark:opacity-[0.18] text-slate-700 dark:text-cyan-300"
          :style="{
            backgroundImage: 'radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)',
            backgroundSize: '28px 28px',
          }"
        />
        <!-- Soft radial glow (only really visible in dark mode) -->
        <div class="pointer-events-none absolute inset-0 dark:bg-[radial-gradient(ellipse_at_center,rgba(124,58,237,0.18),transparent_60%)]" />
        <NetworkScene />
      </div>
    </section>

    <!-- Featured generations — staff-curated, one per modality. Renders
         nothing when nothing is featured. -->
    <FeaturedShowcase />

    <!-- Code samples - the proof -->
    <section class="relative px-4 sm:px-6 lg:px-8 pb-24">
      <div class="max-w-6xl mx-auto">
        <div class="grid lg:grid-cols-2 gap-8 lg:gap-10 *:min-w-0">
          <!-- Consumer -->
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <div class="h-8 w-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
                <Send class="h-4 w-4 text-white" />
              </div>
              <span class="text-xs font-mono uppercase tracking-wider text-muted-foreground">{{ t('home.forConsumers') }}</span>
            </div>
            <h2 class="text-2xl sm:text-3xl font-bold tracking-tight whitespace-nowrap">
              {{ t('home.consumerTitle') }}
            </h2>
            <i18n-t keypath="home.consumerBody" tag="p" class="text-muted-foreground text-sm sm:text-base" scope="global">
              <template #endpoint>
                <code class="px-1.5 py-0.5 rounded bg-muted font-mono text-foreground text-xs">api.inference.club/v1</code>
              </template>
            </i18n-t>
            <CodeTabs :snippets="consumerSnippets" filename="consumer" />
          </div>

          <!-- Provider -->
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <div class="h-8 w-8 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                <Cpu class="h-4 w-4 text-white" />
              </div>
              <span class="text-xs font-mono uppercase tracking-wider text-muted-foreground">{{ t('home.forProviders') }}</span>
            </div>
            <h2 class="text-2xl sm:text-3xl font-bold tracking-tight whitespace-nowrap">
              {{ t('home.providerTitle') }}
            </h2>
            <i18n-t keypath="home.providerBody" tag="p" class="text-muted-foreground text-sm sm:text-base" scope="global">
              <template #vllm>
                <code class="px-1.5 py-0.5 rounded bg-muted font-mono text-foreground text-xs">vllm</code>
              </template>
              <template #llamacpp>
                <code class="px-1.5 py-0.5 rounded bg-muted font-mono text-foreground text-xs">llama.cpp</code>
              </template>
              <template #ollama>
                <code class="px-1.5 py-0.5 rounded bg-muted font-mono text-foreground text-xs">ollama</code>
              </template>
            </i18n-t>
            <CodeTabs :snippets="providerSnippets" filename="provider" />
          </div>
        </div>
      </div>
    </section>

    <!-- Architecture diagram -->
    <section class="relative px-4 sm:px-6 lg:px-8 py-24 border-y bg-muted/30">
      <div class="max-w-6xl mx-auto">
        <div class="text-center mb-14">
          <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">{{ t('home.archEyebrow') }}</p>
          <h2 class="text-3xl sm:text-4xl font-bold tracking-tight">
            {{ t('home.archTitleLead') }} <span class="text-muted-foreground font-normal">{{ t('home.archTitleMuted') }}</span>
          </h2>
        </div>

        <div class="grid md:grid-cols-3 gap-6 relative">
          <!-- Step 1 -->
          <div class="group relative rounded-xl border bg-card p-6 hover:border-violet-500/40 transition-colors">
            <div class="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full bg-background border px-2.5 py-0.5 text-xs font-mono">
              <span class="text-muted-foreground">{{ t('home.step') }}</span>
              <span class="bg-gradient-to-r from-violet-500 to-fuchsia-500 bg-clip-text text-transparent font-semibold">01</span>
            </div>
            <Cpu class="h-7 w-7 text-violet-500 mb-4 mt-2" />
            <h3 class="font-semibold text-lg mb-2">{{ t('home.step1Title') }}</h3>
            <i18n-t keypath="home.step1Body" tag="p" class="text-sm text-muted-foreground leading-relaxed" scope="global">
              <template #agent>
                <code class="font-mono text-foreground text-xs">inference-club-agent</code>
              </template>
            </i18n-t>
          </div>
          <!-- Step 2 -->
          <div class="group relative rounded-xl border bg-card p-6 hover:border-fuchsia-500/40 transition-colors">
            <div class="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full bg-background border px-2.5 py-0.5 text-xs font-mono">
              <span class="text-muted-foreground">{{ t('home.step') }}</span>
              <span class="bg-gradient-to-r from-fuchsia-500 to-cyan-500 bg-clip-text text-transparent font-semibold">02</span>
            </div>
            <Network class="h-7 w-7 text-fuchsia-500 mb-4 mt-2" />
            <h3 class="font-semibold text-lg mb-2">{{ t('home.step2Title') }}</h3>
            <p class="text-sm text-muted-foreground leading-relaxed">
              {{ t('home.step2Body') }}
            </p>
          </div>
          <!-- Step 3 -->
          <div class="group relative rounded-xl border bg-card p-6 hover:border-cyan-500/40 transition-colors">
            <div class="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full bg-background border px-2.5 py-0.5 text-xs font-mono">
              <span class="text-muted-foreground">{{ t('home.step') }}</span>
              <span class="bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent font-semibold">03</span>
            </div>
            <Send class="h-7 w-7 text-cyan-500 mb-4 mt-2" />
            <h3 class="font-semibold text-lg mb-2">{{ t('home.step3Title') }}</h3>
            <i18n-t keypath="home.step3Body" tag="p" class="text-sm text-muted-foreground leading-relaxed" scope="global">
              <template #endpoint>
                <code class="font-mono text-foreground text-xs">api.inference.club</code>
              </template>
            </i18n-t>
          </div>
        </div>

        <!-- Topology mini-diagram -->
        <div class="mt-16 mx-auto max-w-3xl">
          <svg
            viewBox="0 0 600 220"
            class="w-full h-auto text-muted-foreground"
            fill="none"
            stroke="currentColor"
            stroke-width="1.2"
          >
            <defs>
              <linearGradient id="flow" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="rgb(139 92 246)" />
                <stop offset="50%" stop-color="rgb(217 70 239)" />
                <stop offset="100%" stop-color="rgb(34 211 238)" />
              </linearGradient>
              <filter id="glow"><feGaussianBlur stdDeviation="1.4" /></filter>
            </defs>

            <!-- left: gpu nodes -->
            <g>
              <rect x="20" y="30"  width="120" height="36" rx="8" fill="rgba(139,92,246,0.06)" stroke="rgba(139,92,246,0.5)" />
              <text x="80" y="53" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="currentColor" stroke="none">brian's 4090</text>
              <rect x="20" y="92"  width="120" height="36" rx="8" fill="rgba(217,70,239,0.06)" stroke="rgba(217,70,239,0.5)" />
              <text x="80" y="115" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="currentColor" stroke="none">m3 ultra · 192gb</text>
              <rect x="20" y="154" width="120" height="36" rx="8" fill="rgba(34,211,238,0.06)" stroke="rgba(34,211,238,0.5)" />
              <text x="80" y="177" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="currentColor" stroke="none">2× 3090 rig</text>
            </g>

            <!-- center: tailnet -->
            <g>
              <rect x="220" y="80" width="160" height="60" rx="12" fill="rgba(0,0,0,0)" stroke="url(#flow)" stroke-width="1.5" />
              <text x="300" y="105" text-anchor="middle" font-family="ui-monospace,monospace" font-size="12" fill="currentColor" stroke="none">inference.club</text>
              <text x="300" y="124" text-anchor="middle" font-family="ui-monospace,monospace" font-size="10" fill="currentColor" opacity="0.6" stroke="none">private tailnet</text>
            </g>

            <!-- right: api + dev -->
            <g>
              <rect x="450" y="60" width="130" height="36" rx="8" fill="rgba(0,0,0,0)" stroke="currentColor" />
              <text x="515" y="83" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="currentColor" stroke="none">api.inference.club</text>
              <rect x="450" y="124" width="130" height="36" rx="8" fill="rgba(0,0,0,0)" stroke="currentColor" />
              <text x="515" y="147" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="currentColor" stroke="none">your code</text>
            </g>

            <!-- lines -->
            <path d="M140 48 C 180 48, 200 100, 220 110" stroke="url(#flow)" stroke-width="1.4" fill="none" />
            <path d="M140 110 L 220 110" stroke="url(#flow)" stroke-width="1.4" fill="none" />
            <path d="M140 172 C 180 172, 200 120, 220 110" stroke="url(#flow)" stroke-width="1.4" fill="none" />
            <path d="M380 100 C 410 90, 420 80, 450 78" stroke="url(#flow)" stroke-width="1.4" fill="none" />
            <path d="M515 96 L 515 124" stroke="currentColor" stroke-dasharray="3 3" />
          </svg>
        </div>
      </div>
    </section>

    <!-- Why -->
    <section class="px-4 sm:px-6 lg:px-8 py-24">
      <div class="max-w-6xl mx-auto">
        <div class="text-center mb-14">
          <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">{{ t('home.whyEyebrow') }}</p>
          <h2 class="text-3xl sm:text-4xl font-bold tracking-tight">
            {{ t('home.whyTitleLead') }}
            <span class="bg-gradient-to-r from-violet-500 to-cyan-500 bg-clip-text text-transparent">{{ t('home.whyTitleHighlight') }}</span>
            {{ t('home.whyTitleTrail') }}
          </h2>
        </div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <div
            v-for="f in features"
            :key="f.title"
            class="group rounded-xl border bg-card p-6 hover:shadow-lg transition-all"
          >
            <div
              class="h-10 w-10 rounded-lg bg-gradient-to-br flex items-center justify-center mb-4"
              :class="f.grad"
            >
              <component :is="f.icon" class="h-5 w-5 text-white" />
            </div>
            <h3 class="font-semibold mb-1.5">{{ t(`home.${f.key}Title`) }}</h3>
            <p class="text-sm text-muted-foreground leading-relaxed">{{ t(`home.${f.key}Body`) }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- From the blog -->
    <section v-if="featuredPost" class="relative px-4 sm:px-6 lg:px-8 py-20 border-t">
      <div class="max-w-5xl mx-auto">
        <div class="flex items-end justify-between mb-8">
          <h2 class="text-2xl sm:text-3xl font-bold tracking-tight">{{ t('home.blogEyebrow') }}</h2>
          <NuxtLink
            :to="localePath('/blog')"
            class="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          >
            {{ t('common.allPosts') }} <ArrowRight class="h-3.5 w-3.5" />
          </NuxtLink>
        </div>
        <NuxtLink
          :to="localePath(featuredPost.path)"
          class="group block rounded-2xl border bg-card overflow-hidden shadow-sm hover:shadow-lg hover:border-primary/40 transition-all"
        >
          <div class="grid md:grid-cols-2">
            <div class="relative aspect-[16/10] md:aspect-auto md:min-h-[18rem] overflow-hidden">
              <img
                v-if="featuredPost.image"
                :src="featuredPost.image"
                :alt="featuredPost.title"
                class="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
              >
              <div
                v-else
                class="absolute inset-0 bg-gradient-to-br from-violet-500/30 via-fuchsia-500/20 to-cyan-500/30"
              />
            </div>
            <div class="p-6 sm:p-8 flex flex-col justify-center">
              <p class="text-xs uppercase tracking-wide text-primary font-medium mb-2">{{ t('home.featured') }}</p>
              <h3 class="text-xl sm:text-2xl font-bold tracking-tight group-hover:text-primary transition-colors">
                {{ featuredPost.title }}
              </h3>
              <p v-if="featuredPost.description" class="mt-3 text-muted-foreground line-clamp-3">
                {{ featuredPost.description }}
              </p>
              <div v-if="featuredPost.tags?.length" class="mt-5 flex flex-wrap gap-1.5">
                <span
                  v-for="tag in featuredPost.tags"
                  :key="tag"
                  class="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground"
                >
                  #{{ tag }}
                </span>
              </div>
              <span class="mt-6 inline-flex items-center gap-1 text-sm font-medium text-primary">
                {{ t('common.readArticle') }} <ArrowRight class="h-4 w-4" />
              </span>
            </div>
          </div>
        </NuxtLink>
      </div>
    </section>

    <!-- Final CTA -->
    <section class="relative px-4 sm:px-6 lg:px-8 py-24 border-t overflow-hidden">
      <div
        class="pointer-events-none absolute inset-0 -z-10 opacity-60"
        style="background: radial-gradient(ellipse at center, rgba(139,92,246,0.12), transparent 60%)"
      />
      <div class="max-w-3xl mx-auto text-center">
        <Zap class="h-10 w-10 mx-auto mb-6 text-violet-500" />
        <h2 class="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
          {{ t('home.ctaTitle') }}
        </h2>
        <p class="text-muted-foreground text-lg mb-10 max-w-xl mx-auto">
          {{ t('home.ctaBody') }}
        </p>
        <div class="flex flex-col sm:flex-row gap-3 justify-center">
          <NuxtLink :to="localePath(isAuthenticated ? '/dashboard' : '/login')">
            <Button size="lg" class="w-full sm:w-auto h-12 px-6 text-base shadow-lg shadow-violet-500/20">
              {{ isAuthenticated ? t('home.goToDashboard') : t('home.getApiKey') }}
              <ArrowRight class="ml-2 h-4 w-4" />
            </Button>
          </NuxtLink>
          <NuxtLink :to="localePath('/docs')">
            <Button size="lg" variant="outline" class="w-full sm:w-auto h-12 px-6 text-base">
              {{ t('common.readTheDocs') }}
            </Button>
          </NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>

