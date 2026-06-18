import { defineStore } from 'pinia'
import {
  useChatThreads,
  type ChatThreadSummary,
  type ChatThreadDetail,
} from '@/composables/useChatThreads'

interface PaginationState {
  count: number
  next: string | null
  previous: string | null
}

export const useChatThreadStore = defineStore('chatThread', {
  state: () => ({
    threads: [] as ChatThreadSummary[],
    loading: false,
    error: null as string | null,
    pagination: { count: 0, next: null, previous: null } as PaginationState,
    currentThread: null as ChatThreadDetail | null,
  }),

  actions: {
    async fetchThreads(limit = 10, offset = 0) {
      const { listThreads } = useChatThreads()
      this.loading = true
      this.error = null
      try {
        const res = await listThreads(limit, offset)
        this.threads = res.results
        this.pagination = { count: res.count, next: res.next, previous: res.previous }
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to fetch chats'
        this.pagination = { count: 0, next: null, previous: null }
      } finally {
        this.loading = false
      }
    },

    async fetchThread(id: string) {
      const { getThread } = useChatThreads()
      this.loading = true
      this.error = null
      this.currentThread = null
      try {
        this.currentThread = await getThread(id)
        return this.currentThread
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to fetch chat'
        throw e
      } finally {
        this.loading = false
      }
    },

    async deleteThread(id: string) {
      const { deleteThread } = useChatThreads()
      await deleteThread(id)
      this.threads = this.threads.filter((t) => t.public_id !== id)
      this.pagination.count = Math.max(0, this.pagination.count - 1)
      if (this.currentThread?.public_id === id) this.currentThread = null
    },
  },
})
