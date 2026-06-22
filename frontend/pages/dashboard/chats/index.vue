<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { MessagesSquare, Sparkles, Trash2, ArrowUpDown } from 'lucide-vue-next'
import { useChatThreadStore } from '@/stores/chatThread'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'

definePageMeta({ layout: 'app' })

const store = useChatThreadStore()
const pagination = usePagination(computed(() => store.pagination.count), 10)

watch([pagination.currentPage, pagination.currentPageSize], ([page, size]) => {
  store.fetchThreads(size, (page - 1) * size)
})

const deletingId = ref<string | null>(null)
const remove = async (id: string) => {
  deletingId.value = id
  try {
    await store.deleteThread(id)
    toast.success('Chat deleted')
  } catch {
    toast.error('Failed to delete chat')
  } finally {
    deletingId.value = null
  }
}

// Compact relative time ("3h ago", "2d ago").
const rel = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.round(diff / 1000)
  if (s < 60) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

const fmt = (n: number) => Intl.NumberFormat().format(n)

// Badge for which surface produced the thread.
const SOURCE_LABEL: Record<string, string> = { chat: 'Chat', agent: 'Agent', voice: 'Voice' }
const sourceLabel = (s?: string) => SOURCE_LABEL[s || 'chat'] || 'Chat'

onMounted(() => store.fetchThreads(pagination.currentPageSize.value, 0))
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-3 sm:px-6 py-6">
    <div class="flex flex-wrap items-end justify-between gap-y-2 mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <MessagesSquare class="size-6" /> Chats
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          {{ store.pagination.count }} saved conversation{{ store.pagination.count === 1 ? '' : 's' }}
        </p>
      </div>
      <NuxtLink to="/dashboard/playground">
        <Button size="sm" class="gap-1.5">
          <Sparkles class="size-4" /> New chat
        </Button>
      </NuxtLink>
    </div>

    <!-- Loading skeleton -->
    <div v-if="store.loading && store.threads.length === 0" class="space-y-3">
      <Card v-for="i in 4" :key="i" class="p-4 animate-pulse">
        <div class="h-5 bg-muted rounded w-1/2 mb-3" />
        <div class="h-3 bg-muted rounded w-1/3" />
      </Card>
    </div>

    <div v-else-if="store.error" class="text-destructive text-center py-8">{{ store.error }}</div>

    <div v-else-if="store.threads.length === 0" class="text-center py-16 text-muted-foreground">
      <MessagesSquare class="size-10 mx-auto mb-3 opacity-40" />
      <p class="text-sm">No chats yet.</p>
      <NuxtLink to="/dashboard/playground" class="text-sm text-primary hover:underline">
        Start a conversation in the playground →
      </NuxtLink>
    </div>

    <div v-else class="space-y-3">
      <PaginationControls
        v-if="pagination.pageCount.value > 1"
        :current-page="pagination.currentPage.value"
        :current-page-size="pagination.currentPageSize.value"
        :page-count="pagination.pageCount.value"
        :visible-pages="pagination.visiblePages.value"
        :is-first-page="pagination.isFirstPage.value"
        :is-last-page="pagination.isLastPage.value"
        :prev="pagination.prev"
        :next="pagination.next"
        :on-page-change="(page) => { pagination.currentPage.value = page }"
      />

      <Card
        v-for="t in store.threads"
        :key="t.public_id"
        class="p-4 hover:bg-muted/30 transition-colors group"
      >
        <div class="flex items-start justify-between gap-3">
          <NuxtLink :to="`/dashboard/chats/${t.public_id}`" class="min-w-0 flex-1">
            <h2 class="font-medium truncate flex items-center gap-2">
              <Badge
                variant="outline"
                class="shrink-0 text-[10px] px-1.5 py-0"
                :class="{
                  'border-violet-400/50 text-violet-600 dark:text-violet-400': t.source === 'voice',
                  'border-sky-400/50 text-sky-600 dark:text-sky-400': t.source === 'agent',
                }"
              >{{ sourceLabel(t.source) }}</Badge>
              <span v-if="t.title" class="truncate">{{ t.title }}</span>
              <span v-else class="text-muted-foreground italic truncate">Untitled {{ sourceLabel(t.source).toLowerCase() }}</span>
            </h2>
            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span class="font-mono truncate max-w-[16rem]">{{ t.model || '—' }}</span>
              <span class="inline-flex items-center gap-1">
                <ArrowUpDown class="size-3" /> {{ t.message_count }} msg{{ t.message_count === 1 ? '' : 's' }}
              </span>
              <span v-if="t.total_tokens">{{ fmt(t.total_tokens) }} tok</span>
              <Badge v-if="t.has_logprobs" variant="secondary" class="text-[10px] px-1.5 py-0">logprobs</Badge>
              <span>{{ rel(t.modified_on) }}</span>
            </div>
          </NuxtLink>
          <Button
            variant="ghost"
            size="icon"
            class="size-8 text-muted-foreground hover:text-destructive opacity-60 group-hover:opacity-100"
            :disabled="deletingId === t.public_id"
            title="Delete chat"
            @click="remove(t.public_id)"
          >
            <Trash2 class="size-4" />
          </Button>
        </div>
      </Card>

      <PaginationControls
        v-if="pagination.pageCount.value > 1"
        :current-page="pagination.currentPage.value"
        :current-page-size="pagination.currentPageSize.value"
        :page-count="pagination.pageCount.value"
        :visible-pages="pagination.visiblePages.value"
        :is-first-page="pagination.isFirstPage.value"
        :is-last-page="pagination.isLastPage.value"
        :prev="pagination.prev"
        :next="pagination.next"
        :on-page-change="(page) => { pagination.currentPage.value = page }"
      />
    </div>
  </div>
</template>
