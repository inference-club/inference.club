<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Bot, Sparkles, User } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useChatThreadStore } from '@/stores/chatThread'

definePageMeta({ layout: 'app' })

const route = useRoute()
const store = useChatThreadStore()
const id = computed(() => String(route.params.id))

// When any turn carries logprobs, offer the confidence heat-map (same renderer
// as the live playground). On by default here since you came to inspect.
const showLogprobs = ref(true)
const thread = computed(() => store.currentThread)
const hasLogprobs = computed(() => !!thread.value?.has_logprobs)

const fmt = (n: number) => Intl.NumberFormat().format(n)

onMounted(() => store.fetchThread(id.value).catch(() => {}))
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
          <span v-else class="text-muted-foreground italic">Untitled chat</span>
        </h1>
        <NuxtLink :to="`/dashboard/playground?thread=${thread.public_id}`">
          <Button size="sm" variant="outline" class="gap-1.5">
            <Sparkles class="size-4" /> Continue in playground
          </Button>
        </NuxtLink>
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

            <pre
              v-if="m.role === 'user'"
              class="text-sm whitespace-pre-wrap font-sans"
            >{{ m.content }}</pre>
            <LogprobText
              v-else-if="showLogprobs && m.logprobs?.length"
              :tokens="m.logprobs"
            />
            <MarkdownRenderer v-else :content="m.content" />

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
