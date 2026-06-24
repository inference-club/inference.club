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
          <p class="mt-5 text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            {{ t('home.archSubtitle') }}
          </p>
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

        <!-- Detailed conceptual networking + architecture diagram -->
        <div class="mt-16">
          <ArchitectureDiagram />
        </div>
      </div>
    </section>

    <!-- inference.club, the whole stack, in one run-on sentence -->
    <StreamOfConsciousness />

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
        <!-- Community: join the conversation -->
        <div class="mt-10 flex items-center justify-center gap-6 text-muted-foreground">
          <a href="https://discord.gg/4fVcmJq4X" target="_blank" rel="noopener" aria-label="Discord" class="transition hover:text-primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" viewBox="0 0 16 16">
              <path d="M13.545 2.907a13.2 13.2 0 0 0-3.257-1.011.05.05 0 0 0-.052.025c-.141.25-.297.577-.406.833a12.2 12.2 0 0 0-3.658 0 8 8 0 0 0-.412-.833.05.05 0 0 0-.052-.025c-1.125.194-2.22.534-3.257 1.011a.04.04 0 0 0-.021.018C.356 6.024-.213 9.047.066 12.032q.003.022.021.037a13.3 13.3 0 0 0 3.995 2.02.05.05 0 0 0 .056-.019q.463-.63.818-1.329a.05.05 0 0 0-.01-.059l-.018-.011a9 9 0 0 1-1.248-.595.05.05 0 0 1-.02-.066l.015-.019q.127-.095.248-.195a.05.05 0 0 1 .051-.007c2.619 1.196 5.454 1.196 8.041 0a.05.05 0 0 1 .053.007q.121.1.248.195a.05.05 0 0 1-.004.085 8 8 0 0 1-1.249.594.05.05 0 0 0-.03.03.05.05 0 0 0 .003.041c.24.465.515.909.817 1.329a.05.05 0 0 0 .056.019 13.2 13.2 0 0 0 4.001-2.02.05.05 0 0 0 .021-.037c.334-3.451-.559-6.449-2.366-9.106a.03.03 0 0 0-.02-.019m-8.198 7.307c-.789 0-1.438-.724-1.438-1.612s.637-1.613 1.438-1.613c.807 0 1.45.73 1.438 1.613 0 .888-.637 1.612-1.438 1.612m5.316 0c-.788 0-1.438-.724-1.438-1.612s.637-1.613 1.438-1.613c.807 0 1.451.73 1.438 1.613 0 .888-.631 1.612-1.438 1.612"/>
            </svg>
          </a>
          <a href="https://github.com/inference-club" target="_blank" rel="noopener" aria-label="GitHub" class="transition hover:text-primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" viewBox="0 0 16 16">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/>
            </svg>
          </a>
          <a href="https://x.com/briancaffey" target="_blank" rel="noopener" aria-label="X / Twitter" class="text-xl leading-none transition hover:text-primary">
            𝕏
          </a>
        </div>
      </div>
    </section>
  </div>
</template>

