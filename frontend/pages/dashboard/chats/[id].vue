<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, Bot, Sparkles, User, Play, Pause, Square, Volume2, Wand2, Wrench } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useChatThreadStore } from '@/stores/chatThread'
import { useConversationPlayer } from '@/composables/useConversationPlayer'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.chats' })

const route = useRoute()
const store = useChatThreadStore()
const id = computed(() => String(route.params.id))

// When any turn carries logprobs, offer the confidence heat-map (same renderer
// as the live playground). On by default here since you came to inspect.
const showLogprobs = ref(true)
const thread = computed(() => store.currentThread)
const hasLogprobs = computed(() => !!thread.value?.has_logprobs)

const fmt = (n: number) => Intl.NumberFormat().format(n)

// Route "Continue" back to the surface that produced the thread.
const CONTINUE = {
  chat: { path: '/dashboard/playground', label: 'Continue in playground', icon: Sparkles },
  agent: { path: '/dashboard/playground/agent', label: 'Continue in agent', icon: Wand2 },
  voice: { path: '/dashboard/playground/voice', label: 'Continue in voice', icon: Volume2 },
} as const
const cont = computed(() => CONTINUE[(thread.value?.source as keyof typeof CONTINUE) || 'chat'])

// Audio replay for voice sessions (per-message + call-style play-all).
const player = useConversationPlayer()
const messages = computed(() => thread.value?.messages || [])
const hasAudio = computed(() => messages.value.some((m) => m.audio?.length))
const toolLabel = (name: string) => name.replace(/_/g, ' ')

const playMessage = (i: number) => {
  if (player.activeMsg.value === i && player.playing.value && !player.paused.value) player.pause()
  else if (player.activeMsg.value === i && player.paused.value) player.resume()
  else void player.playOne(messages.value, i)
}

onMounted(() => store.fetchThread(id.value).catch(() => {}))
onBeforeUnmount(() => player.dispose())
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 sm:px-6 py-6">
    <NuxtLink
      to="/dashboard/chats"
      class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
    >
      <ArrowLeft class="size-4" /> All chats
    </NuxtLink>

    <div v-if="store.loading && !thread" class="space-y-4">
      <div class="h-7 bg-muted rounded w-1/2 animate-pulse" />
      <Card v-for="i in 2" :key="i" class="p-4 animate-pulse">
        <div class="h-4 bg-muted rounded w-3/4 mb-2" />
        <div class="h-4 bg-muted rounded w-1/2" />
      </Card>
    </div>

    <div v-else-if="store.error" class="text-destructive text-center py-8">{{ store.error }}</div>

    <template v-else-if="thread">
      <!-- Header -->
      <div class="flex flex-wrap items-start justify-between gap-3 mb-2">
        <h1 class="text-2xl font-semibold tracking-tight min-w-0">
          <span v-if="thread.title">{{ thread.title }}</span>
          <span v-else class="text-muted-foreground italic">Untitled {{ (thread.source || 'chat') }}</span>
        </h1>
        <div class="flex items-center gap-2">
          <Button
            v-if="hasAudio"
            size="sm"
            variant="ghost"
            class="gap-1.5"
            :title="player.playing.value ? 'Stop' : 'Play the whole conversation'"
            @click="player.playing.value ? player.stop() : player.playFrom(messages, 0)"
          >
            <Square v-if="player.playing.value" class="size-4" />
            <Play v-else class="size-4" /> Play all
          </Button>
          <NuxtLink :to="`${cont.path}?thread=${thread.public_id}`">
            <Button size="sm" variant="outline" class="gap-1.5">
              <component :is="cont.icon" class="size-4" /> {{ cont.label }}
            </Button>
          </NuxtLink>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground mb-4">
        <span class="font-mono truncate max-w-[18rem]">{{ thread.model || '—' }}</span>
        <span>{{ thread.message_count }} messages</span>
        <span v-if="thread.total_tokens">{{ fmt(thread.total_tokens) }} tokens</span>
        <label v-if="hasLogprobs" class="inline-flex items-center gap-1.5 cursor-pointer">
          <Switch id="logprobs-view" v-model="showLogprobs" />
          <span>Show logprobs</span>
        </label>
      </div>

      <!-- Conversation -->
      <div class="space-y-4">
        <div v-for="(m, i) in thread.messages" :key="i" class="flex gap-3">
          <div
            class="size-8 shrink-0 rounded-full flex items-center justify-center"
            :class="m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'"
          >
            <User v-if="m.role === 'user'" class="size-4" />
            <Bot v-else class="size-4" />
          </div>
          <div class="min-w-0 flex-1 pt-1 space-y-2">
            <!-- Reasoning trace — heat-mapped here when logprobs are on. -->
            <details
              v-if="m.reasoning"
              class="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20"
            >
              <summary class="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                Thinking
              </summary>
              <LogprobText
                v-if="showLogprobs && m.reasoningLogprobs?.length"
                :tokens="m.reasoningLogprobs"
                class="px-3 pb-2"
              />
              <pre v-else class="px-3 pb-2 text-xs whitespace-pre-wrap text-amber-900/80 dark:text-amber-200/70 font-sans">{{ m.reasoning }}</pre>
            </details>

            <!-- Tool traces (agent sessions) -->
            <div v-for="(c, ci) in m.tools" :key="`tool-${ci}`" class="rounded-lg border bg-muted/30 text-sm">
              <div class="flex items-center gap-2 px-3 py-2">
                <Wrench class="size-4 text-muted-foreground shrink-0" />
                <span class="font-medium">{{ toolLabel(c.name) }}</span>
                <span class="truncate text-xs text-muted-foreground">
                  {{ (c.arguments?.query || c.arguments?.prompt || c.arguments?.input || '') as string }}
                </span>
                <span v-if="c.ok === false" class="ml-auto text-xs text-destructive">failed</span>
              </div>
              <div v-if="c.media?.length" class="flex flex-wrap gap-2 px-3 pb-3">
                <template v-for="item in c.media" :key="item.id">
                  <img v-if="item.kind === 'image'" :src="item.url" alt="generated image" class="max-h-56 rounded-md border" />
                  <video v-else-if="item.kind === 'video'" :src="item.url" controls class="max-h-56 rounded-md border" />
                  <audio v-else :src="item.url" controls class="w-full" />
                </template>
              </div>
              <details v-else-if="c.summary" class="px-3 pb-2">
                <summary class="cursor-pointer text-xs text-muted-foreground">Details</summary>
                <pre class="mt-1 text-xs whitespace-pre-wrap text-muted-foreground font-sans">{{ c.summary }}</pre>
              </details>
            </div>

            <!-- User-uploaded attachments (image / audio / video) -->
            <div v-if="m.attachments?.length" class="flex flex-wrap gap-2">
              <template v-for="(a, ai) in m.attachments" :key="`att-${ai}`">
                <img v-if="a.kind === 'image'" :src="a.url" :alt="a.name" class="max-h-56 rounded-md border" />
                <video v-else-if="a.kind === 'video'" :src="a.url" controls class="max-h-56 rounded-md border" />
                <audio v-else :src="a.url" controls class="w-full" />
              </template>
            </div>

            <!-- Body, with a per-message replay button when audio is stored -->
            <div class="flex items-start gap-2">
              <button
                v-if="m.audio?.length"
                type="button"
                class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border text-muted-foreground hover:text-foreground transition"
                :class="player.activeMsg.value === i && player.playing.value && !player.paused.value ? 'bg-primary text-primary-foreground border-transparent' : ''"
                :title="player.activeMsg.value === i ? 'Pause' : 'Play this message'"
                @click="playMessage(i)"
              >
                <Pause v-if="player.activeMsg.value === i && player.playing.value && !player.paused.value" class="size-3.5" />
                <Play v-else class="size-3.5" />
              </button>
              <div class="min-w-0 flex-1">
                <pre
                  v-if="m.role === 'user'"
                  class="text-sm whitespace-pre-wrap font-sans"
                >{{ m.content }}</pre>
                <LogprobText
                  v-else-if="showLogprobs && m.logprobs?.length"
                  :tokens="m.logprobs"
                />
                <MarkdownRenderer v-else :content="m.content" />
              </div>
            </div>

            <div
              v-if="m.role === 'assistant' && m.usage"
              class="flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground"
            >
              <span v-if="m.usage.prompt_tokens != null">↑ {{ m.usage.prompt_tokens }} in</span>
              <span v-if="m.usage.completion_tokens != null">↓ {{ m.usage.completion_tokens }} out</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
