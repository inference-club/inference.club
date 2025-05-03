import { defineStore } from 'pinia'
import type { InferenceRequest } from '@/types'
import { useInferenceRequest } from '@/composables/useInferenceRequest'

interface PaginationState {
  count: number
  next: string | null
  previous: string | null
}

export const useInferenceRequestStore = defineStore('inferenceRequest', {
  state: () => ({
    requests: [] as InferenceRequest[],
    loading: false,
    error: null as string | null,
    pagination: {
      count: 0,
      next: null,
      previous: null,
    } as PaginationState,
  }),

  getters: {
    hasNextPage: (state) => !!state.pagination.next,
    hasPreviousPage: (state) => !!state.pagination.previous,
  },

  actions: {
    async fetchRequests(limit: number = 10, offset: number = 0) {
      const { listInferenceRequests, loading, error } = useInferenceRequest()
      this.loading = loading.value
      this.error = error.value

      try {
        const response = await listInferenceRequests(limit, offset)
        this.requests = response.results
        this.pagination = {
          count: response.count,
          next: response.next,
          previous: response.previous,
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to fetch requests'
        // Reset pagination on error
        this.pagination = {
          count: 0,
          next: null,
          previous: null,
        }
      } finally {
        this.loading = false
      }
    },

    async createRequest(data: Partial<InferenceRequest>) {
      const { createInferenceRequest, loading, error } = useInferenceRequest()
      this.loading = loading.value
      this.error = error.value

      try {
        const newRequest = await createInferenceRequest(data)
        this.requests.unshift(newRequest)
        // Update count after creating new request
        this.pagination.count += 1
        return newRequest
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to create request'
        throw e
      } finally {
        this.loading = false
      }
    },
  },
})