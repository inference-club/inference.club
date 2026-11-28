<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  ArrowRight, ArrowDown, Server, Check, MessageCircle, Code2, Bot, Sparkles, CircleCheck, Hammer, Telescope,
} from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import { useProviders } from '@/composables/useProviders'
import { useTheme } from '@/composables/useTheme'
import { paletteFor, roleColor } from '@/lib/scenes/theme'
import CodeTabs from '@/components/CodeTabs.vue'
import SceneStage from '@/components/scenes/SceneStage.vue'
import { prettyGpuModel } from '@/composables/useMachineForm'
import showcase from '~/public/showcase/index.json'
import models from '~/public/scenes/models/index.json'

const { t, tm, rt, locale } = useI18n()
const localePath = useLocalePath()
const { isAuthenticated } = useAuth()
const list = (key: string) => (tm(key) as unknown[]).map((m) => rt(m as never))

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

// Newest posts, in the active locale with English as the fallback.
const { listMerged } = useLocalizedContent()
const { data: posts } = await useAsyncData(
  'home:posts',
  async () => (await listMerged('blog', q => q.order('publishedAt', 'DESC'))).slice(0, 3),
  { watch: [locale] },
)

// Hero wall: real generations (static files, see scripts/showcase). Two rows
// drifting in opposite directions; the gallery further down has the details.
type Piece = { id: string; kind: string; title: string; thumb?: string; size?: string; gpu?: string | null }
type Model = { id: string; src: string; image?: string | null; points: number; triangles: number; model: string; gpu?: string | null; seconds?: number | null }
const pictures = (showcase.items as Piece[]).filter((p) => p.kind === 'image' && p.thumb)
const half = Math.ceil(pictures.length / 2)
const rows = [pictures.slice(0, half), pictures.slice(half)]
const heroGpu = prettyGpuModel(pictures[0]?.gpu || 'RTX 4090')
// The scenes (see frontend/lib/scenes/README.md). Each is loaded on demand.
const loadSignals = () => import('@/lib/scenes/scenes/signals')
const loadExchange = () => import('@/lib/scenes/scenes/exchange')
const loadNetwork = () => import('@/lib/scenes/scenes/network')
const loadAssemble = () => import('@/lib/scenes/scenes/assemble')
// Real pictures for the mosaic and film strip. A constant, so the scene is
// not rebuilt on every render.
const signalsOptions = {
  art: pictures.filter((p) => !p.id.startsWith('cover-')).slice(0, 8).map((p) => `/showcase/${p.thumb}`),
  models: (models.models as Model[]).map((m) => `/scenes/models/${m.src}`),
}
const lanes = ['text', 'image', 'speech', 'music', 'video', 'shape']
// Real 3D models from the club, sampled to points (scripts/showcase/mesh_points.py).
const shapes = models.models as Model[]
const assembleOptions = { models: shapes.map((m) => ({ src: `/scenes/models/${m.src}`, image: m.image ? `/scenes/models/${m.image}` : null })) }
const shapeOnShow = ref(0)
const onAssembleState = (name: string, value: unknown) => {
  if (name === 'model') shapeOnShow.value = Number(value)
}
const shape = computed(() => shapes[shapeOnShow.value] ?? shapes[0])
// The legend under the exchange scene uses the scene's own colours.
const { isDark } = useTheme()
const role = computed(() => {
  const p = paletteFor(isDark.value)
  return { person: roleColor(p, 'person'), agent: roleColor(p, 'agent'), machine: roleColor(p, 'machine'), private: roleColor(p, 'private') }
})
const households = ref(1)
const onNetworkState = (name: string, value: unknown) => {
  if (name === 'count') households.value = Number(value)
}

const apiSnippets = [
  {
    label: 'curl',
    lang: 'bash',
    code: `curl https://api.inference.club/v1/images/generations \\
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "flux-3-image-klein-fp8",
    "prompt": "a lighthouse in a storm, oil painting",
    "seed": 27015
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
    model="nvidia/nvidia-nemotron-3.5-lightning-30b-a3b-nvfp4",
    messages=[{"role": "user", "content": "four lines about a porch light"}],
)
print(resp.choices[0].message.content)`,
  },
]

const agentSnippets = [
  {
    label: 'MCP',
    lang: 'json',
    code: `{
  "mcpServers": {
    "inference-club": {
      "type": "http",
      "url": "https://api.inference.club/mcp",
      "headers": { "Authorization": "Bearer ic_xxxxxxxxxxxxxxxxxxxx" }
    }
  }
}`,
  },
  {
    label: 'CLI',
    lang: 'bash',
    code: `# Say what you want; get back what was done.
ic.py do "make a 30 second lo-fi song and share it by link"

# Or call one tool directly.
ic.py tool search_library --query "lighthouse"`,
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

const status = computed(() => [
  { key: 'now', icon: CircleCheck, tone: 'text-emerald-500', items: list('landing.status.nowItems') },
  { key: 'soon', icon: Hammer, tone: 'text-amber-500', items: list('landing.status.soonItems') },
  { key: 'next', icon: Telescope, tone: 'text-sky-500', items: list('landing.status.nextItems') },
])
</script>

<template>
  <div class="relative overflow-x-clip">
    <!-- Hero -->
    <section class="relative pt-14 sm:pt-24">
      <div class="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[700px] bg-[radial-gradient(ellipse_at_top,rgba(139,92,246,0.20),transparent_60%)]" />
      <div class="mx-auto max-w-5xl px-4 text-center sm:px-6 lg:px-8">
        <div class="mb-6 inline-flex max-w-full items-center gap-2 rounded-full border bg-background/60 px-3 py-1 text-xs shadow-sm backdrop-blur">
          <span class="relative flex size-2 shrink-0">
            <span class="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span class="relative inline-flex size-2 rounded-full bg-emerald-500" />
          </span>
          <span class="truncate text-muted-foreground">{{ t('landing.hero.badge') }}</span>
        </div>

        <h1 class="text-[2.6rem] font-bold leading-[1.05] tracking-tight sm:text-6xl md:text-7xl" data-testid="hero-title">
          {{ t('landing.hero.titleLead') }}
          <span class="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-amber-400 bg-clip-text text-transparent">
            {{ t('landing.hero.titleHighlight') }}
          </span>
        </h1>

        <p class="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-xl">
          {{ t('landing.hero.subtitle') }}
        </p>

        <div class="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <NuxtLink :to="localePath(isAuthenticated ? '/dashboard' : '/login')">
            <Button size="lg" class="h-12 w-full px-6 text-base shadow-lg shadow-violet-500/20 sm:w-auto">
              {{ isAuthenticated ? t('landing.hero.primaryMember') : t('landing.hero.primary') }}
              <ArrowRight class="ml-2 size-4" />
            </Button>
          </NuxtLink>
          <a href="#signals">
            <Button size="lg" variant="outline" class="h-12 w-full px-6 text-base sm:w-auto">
              {{ t('landing.hero.secondary') }} <ArrowDown class="ml-2 size-4" />
            </Button>
          </a>
        </div>

        <ul class="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-1.5 text-sm text-muted-foreground">
          <li v-for="p in list('landing.hero.points')" :key="p" class="inline-flex items-center gap-1.5">
            <Check class="size-3.5 text-emerald-500" /> {{ p }}
          </li>
        </ul>

        <NuxtLink
          v-if="needsNode"
          :to="localePath('/dashboard')"
          class="mt-6 inline-flex max-w-full items-center gap-2 rounded-full border border-primary/30 bg-primary/[0.06] px-4 py-1.5 text-sm transition-colors hover:bg-primary/10"
        >
          <Server class="size-4 shrink-0 text-primary" />
          <span class="min-w-0 truncate">{{ t('home.needsNode') }}</span>
          <ArrowRight class="size-3.5 shrink-0" />
        </NuxtLink>
      </div>

      <!-- A wall of real generations -->
      <a href="#made-here" class="group mt-12 block space-y-3 sm:mt-16" :aria-label="t('landing.gallery.title')" data-testid="hero-wall">
        <div
          v-for="(row, r) in rows"
          :key="r"
          class="flex w-max gap-3 hero-row"
          :class="r % 2 ? 'hero-row-reverse' : ''"
        >
          <!-- Each row is repeated once so the drift can loop seamlessly. -->
          <template v-for="pass in 2" :key="pass">
            <img
              v-for="p in row"
              :key="`${pass}-${p.id}`"
              :src="`/showcase/${p.thumb}`"
              :alt="pass === 1 ? p.title : ''"
              :aria-hidden="pass === 2 ? 'true' : undefined"
              :loading="r === 0 && pass === 1 ? 'eager' : 'lazy'"
              decoding="async"
              :width="Number((p.size || '1x1').split('x')[0])"
              :height="Number((p.size || '1x1').split('x')[1])"
              class="h-36 w-auto rounded-xl border object-cover shadow-sm sm:h-52 lg:h-60"
            />
          </template>
        </div>
      </a>
      <p class="mt-3 px-4 text-center text-xs text-muted-foreground">
        <Sparkles class="mr-1 inline size-3" />{{ t('landing.hero.madeOn', { gpu: heroGpu }) }}
      </p>
    </section>

    <!-- Made here -->
    <HomeShowcaseGallery />

    <!-- Picked by staff: renders nothing when nothing is featured. -->
    <FeaturedShowcase />

    <!-- Every kind of signal -->
    <HomeSceneSection
      id="signals"
      :eyebrow="t('landing.scenes.signals.eyebrow')"
      :title="t('landing.scenes.signals.title')"
      :body="t('landing.scenes.signals.body')"
    >
      <SceneStage
        :load="loadSignals"
        :options="signalsOptions"
        :label="t('landing.scenes.signals.label')"
        class="h-[34rem] rounded-3xl border sm:h-[36rem]"
      >
        <template #overlay>
          <!-- Lane names sit in HTML so they stay sharp and translatable. Six
               equal rows match the scene's six evenly spaced lanes. -->
          <ul class="absolute inset-y-0 left-0 grid grid-rows-6 pl-4 sm:pl-6">
            <li v-for="lane in lanes" :key="lane" class="flex items-start pt-2">
              <span class="rounded-full bg-[var(--scene-ground)]/70 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider backdrop-blur-sm">
                {{ t(`landing.kinds.${lane}`) }}
              </span>
            </li>
          </ul>
          <div class="absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-[var(--scene-ground)] to-transparent sm:w-20" />
          <div class="absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-[var(--scene-ground)] to-transparent sm:w-20" />
        </template>
      </SceneStage>
    </HomeSceneSection>

    <!-- Watch a model choose its words -->
    <HomeSceneSection
      :eyebrow="t('landing.scenes.thinking.eyebrow')"
      :title="t('landing.scenes.thinking.title')"
      :body="t('landing.scenes.thinking.body')"
    >
      <HomeTokenProbabilities />
    </HomeSceneSection>

    <!-- A picture becomes a 3D model -->
    <HomeSceneSection
      v-if="shapes.length"
      :eyebrow="t('landing.scenes.assemble.eyebrow')"
      :title="t('landing.scenes.assemble.title')"
      :body="t('landing.scenes.assemble.body')"
    >
      <SceneStage
        :load="loadAssemble"
        :options="assembleOptions"
        :label="t('landing.scenes.assemble.label')"
        class="h-[32rem] rounded-3xl border sm:h-[34rem]"
        @state="onAssembleState"
      >
        <template #overlay>
          <p v-if="shape" class="absolute inset-x-4 bottom-3 text-[11px] leading-snug opacity-75 sm:inset-x-6 sm:bottom-5 sm:text-xs" data-testid="assemble-caption">
            <span class="font-mono uppercase tracking-wider">{{ shape.model }}</span>
            <span class="mx-1.5">·</span>
            <span>{{ t('landing.scenes.assemble.caption', { triangles: shape.triangles.toLocaleString(locale), seconds: shape.seconds, gpu: prettyGpuModel(shape.gpu || '') }) }}</span>
            <span class="mx-1.5">·</span>
            <span>{{ t('landing.scenes.assemble.note', { points: shape.points.toLocaleString(locale) }) }}</span>
          </p>
        </template>
      </SceneStage>
    </HomeSceneSection>

    <!-- People and agents ask; machines answer -->
    <HomeSceneSection
      :eyebrow="t('landing.scenes.exchange.eyebrow')"
      :title="t('landing.scenes.exchange.title')"
      :body="t('landing.scenes.exchange.body')"
    >
      <SceneStage
        :load="loadExchange"
        :label="t('landing.scenes.exchange.label')"
        class="aspect-square max-h-[40rem] w-full rounded-3xl border sm:aspect-[16/10]"
      />
      <template #notes>
        <ul class="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
          <li class="inline-flex items-center gap-2"><span class="size-2.5 rounded-full bg-foreground" /> {{ t('landing.scenes.exchange.person') }}</li>
          <li class="inline-flex items-center gap-2"><span class="size-2.5 rotate-45" :style="{ background: role.agent }" /> {{ t('landing.scenes.exchange.agent') }}</li>
          <li class="inline-flex items-center gap-2"><span class="size-3 rounded-[2px] border-2" :style="{ borderColor: role.machine }" /> {{ t('landing.scenes.exchange.machine') }}</li>
          <li class="inline-flex items-center gap-2"><span class="size-3.5 rounded-full border-2 border-dashed" :style="{ borderColor: role.private }" /> {{ t('landing.scenes.exchange.private') }}</li>
        </ul>
      </template>
    </HomeSceneSection>

    <!-- Three ways in -->
    <section class="px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div class="mx-auto max-w-6xl">
        <div class="mb-10 max-w-2xl">
          <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ t('landing.ways.eyebrow') }}</p>
          <h2 class="text-3xl font-bold tracking-tight sm:text-5xl">{{ t('landing.ways.title') }}</h2>
        </div>
        <div class="grid gap-5 lg:grid-cols-3 *:min-w-0">
          <article class="flex flex-col rounded-2xl border bg-card p-5 sm:p-6">
            <span class="mb-4 flex size-10 items-center justify-center rounded-xl bg-fuchsia-500/10 text-fuchsia-500"><MessageCircle class="size-5" /></span>
            <h3 class="text-xl font-semibold">{{ t('landing.ways.ask.title') }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{{ t('landing.ways.ask.body') }}</p>
            <p class="mt-4 rounded-xl rounded-bl-sm bg-primary px-4 py-3 text-sm text-primary-foreground">
              {{ t('landing.ways.ask.example') }}
            </p>
          </article>
          <article class="flex flex-col rounded-2xl border bg-card p-5 sm:p-6">
            <span class="mb-4 flex size-10 items-center justify-center rounded-xl bg-sky-500/10 text-sky-500"><Code2 class="size-5" /></span>
            <h3 class="text-xl font-semibold">{{ t('landing.ways.api.title') }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{{ t('landing.ways.api.body') }}</p>
            <div class="mt-4 min-w-0"><CodeTabs :snippets="apiSnippets" /></div>
          </article>
          <article class="flex flex-col rounded-2xl border bg-card p-5 sm:p-6">
            <span class="mb-4 flex size-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500"><Bot class="size-5" /></span>
            <h3 class="text-xl font-semibold">{{ t('landing.ways.agent.title') }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{{ t('landing.ways.agent.body') }}</p>
            <div class="mt-4 min-w-0"><CodeTabs :snippets="agentSnippets" /></div>
          </article>
        </div>
      </div>
    </section>

    <!-- A network that grows -->
    <HomeSceneSection
      :eyebrow="t('landing.scenes.network.eyebrow')"
      :title="t('landing.scenes.network.title')"
      :body="t('landing.scenes.network.body')"
    >
      <SceneStage
        :load="loadNetwork"
        :label="t('landing.scenes.network.label')"
        class="h-[26rem] rounded-3xl border sm:h-[34rem]"
        @state="onNetworkState"
      >
        <template #overlay>
          <p class="absolute left-4 top-4 sm:left-6 sm:top-6">
            <span class="block text-4xl font-bold tabular-nums sm:text-6xl" data-testid="network-count">{{ households }}</span>
            <span class="font-mono text-[11px] uppercase tracking-wider opacity-70">{{ t('landing.scenes.network.count', households) }}</span>
          </p>
          <p class="absolute bottom-3 right-4 text-[11px] opacity-60 sm:right-6">{{ t('landing.scenes.network.note') }}</p>
        </template>
      </SceneStage>
    </HomeSceneSection>

    <!-- Bring a GPU -->
    <section class="border-y bg-muted/20 px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div class="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-2 *:min-w-0">
        <div>
          <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ t('landing.host.eyebrow') }}</p>
          <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">{{ t('landing.host.title') }}</h2>
          <p class="mt-4 leading-relaxed text-muted-foreground">{{ t('landing.host.body') }}</p>
          <ul class="mt-5 space-y-2 text-sm">
            <li v-for="p in list('landing.host.points')" :key="p" class="flex items-start gap-2">
              <Check class="mt-0.5 size-4 shrink-0 text-emerald-500" /> <span>{{ p }}</span>
            </li>
          </ul>
          <NuxtLink :to="localePath('/docs/providers/run-an-agent')" class="mt-6 inline-block">
            <Button variant="outline" class="gap-2">{{ t('landing.host.cta') }} <ArrowRight class="size-4" /></Button>
          </NuxtLink>
        </div>
        <CodeTabs :snippets="providerSnippets" />
      </div>
    </section>

    <!-- Where it stands -->
    <section class="px-4 py-16 sm:px-6 sm:py-24 lg:px-8" data-testid="status">
      <div class="mx-auto max-w-6xl">
        <div class="mb-10 max-w-2xl">
          <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ t('landing.status.eyebrow') }}</p>
          <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">{{ t('landing.status.title') }}</h2>
        </div>
        <div class="grid gap-5 md:grid-cols-3 *:min-w-0">
          <article v-for="col in status" :key="col.key" class="rounded-2xl border bg-card p-5 sm:p-6">
            <h3 class="mb-4 flex items-center gap-2 font-semibold">
              <component :is="col.icon" class="size-5" :class="col.tone" /> {{ t(`landing.status.${col.key}`) }}
            </h3>
            <ul class="space-y-2.5 text-sm text-muted-foreground">
              <li v-for="item in col.items" :key="item" class="flex items-start gap-2">
                <span class="mt-2 size-1 shrink-0 rounded-full bg-current" /> <span>{{ item }}</span>
              </li>
            </ul>
          </article>
        </div>
      </div>
    </section>

    <!-- From the blog -->
    <section v-if="posts?.length" class="border-t px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
      <div class="mx-auto max-w-6xl">
        <div class="mb-8 flex items-end justify-between gap-4">
          <h2 class="text-2xl font-bold tracking-tight sm:text-3xl">{{ t('landing.blog.title') }}</h2>
          <NuxtLink :to="localePath('/blog')" class="inline-flex shrink-0 items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            {{ t('common.allPosts') }} <ArrowRight class="size-3.5" />
          </NuxtLink>
        </div>
        <div class="grid gap-5 md:grid-cols-3 *:min-w-0">
          <NuxtLink
            v-for="post in posts"
            :key="post.path"
            :to="localePath(post.path)"
            class="group flex flex-col overflow-hidden rounded-2xl border bg-card transition-all hover:border-primary/40 hover:shadow-lg"
          >
            <div class="relative aspect-[16/10] overflow-hidden bg-muted">
              <img
                v-if="post.image"
                :src="post.image"
                :alt="post.title"
                loading="lazy"
                class="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
              >
              <div v-else class="absolute inset-0 bg-gradient-to-br from-violet-500/30 via-fuchsia-500/20 to-cyan-500/30" />
            </div>
            <div class="flex flex-1 flex-col p-5">
              <h3 class="font-semibold tracking-tight group-hover:text-primary">{{ post.title }}</h3>
              <p v-if="post.description" class="mt-2 line-clamp-3 text-sm text-muted-foreground">{{ post.description }}</p>
              <span class="mt-auto inline-flex items-center gap-1 pt-4 text-sm font-medium text-primary">
                {{ t('common.readArticle') }} <ArrowRight class="size-4" />
              </span>
            </div>
          </NuxtLink>
        </div>
      </div>
    </section>

    <!-- Final call -->
    <section class="relative overflow-hidden border-t px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
      <div class="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_bottom,rgba(217,70,239,0.16),transparent_60%)]" />
      <div class="mx-auto max-w-2xl text-center">
        <h2 class="text-4xl font-bold tracking-tight sm:text-5xl">{{ t('landing.cta.title') }}</h2>
        <p class="mt-4 text-muted-foreground">{{ t('landing.cta.body') }}</p>
        <div class="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <NuxtLink :to="localePath(isAuthenticated ? '/dashboard' : '/login')">
            <Button size="lg" class="h-12 w-full px-6 text-base sm:w-auto">
              {{ isAuthenticated ? t('landing.hero.primaryMember') : t('landing.cta.primary') }} <ArrowRight class="ml-2 size-4" />
            </Button>
          </NuxtLink>
          <NuxtLink :to="localePath('/docs')">
            <Button size="lg" variant="outline" class="h-12 w-full px-6 text-base sm:w-auto">{{ t('landing.cta.secondary') }}</Button>
          </NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* The hero wall: two rows drifting slowly in opposite directions. Each row
   holds its pictures twice, so shifting by half its width loops cleanly. */
.hero-row {
  animation: hero-drift 70s linear infinite;
}
.hero-row-reverse {
  animation-direction: reverse;
}
.group:hover .hero-row {
  animation-play-state: paused;
}
@keyframes hero-drift {
  from { transform: translateX(0); }
  to { transform: translateX(calc(-50% - 0.375rem)); }
}
@media (prefers-reduced-motion: reduce) {
  .hero-row { animation: none; }
}
</style>
