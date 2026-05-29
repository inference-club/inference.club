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
    // Network-wide list ("All Inference Requests") — kept separate from the
    // user's own list so the two pages paginate independently.
    allRequests: [] as InferenceRequest[],
    allPagination: {
      count: 0,
      next: null,
      previous: null,
    } as PaginationState,
    currentRequest: null as InferenceRequest | null,
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

    async fetchAllRequests(limit: number = 10, offset: number = 0) {
      const { listAllInferenceRequests } = useInferenceRequest()
      this.loading = true
      this.error = null
      try {
        const response = await listAllInferenceRequests(limit, offset)
        this.allRequests = response.results
        this.allPagination = {
          count: response.count,
          next: response.next,
          previous: response.previous,
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to fetch requests'
        this.allPagination = { count: 0, next: null, previous: null }
      } finally {
        this.loading = false
      }
    },

    async fetchRequest(id: string) {
      const { getInferenceRequest } = useInferenceRequest()
      this.loading = true
      this.error = null
      this.currentRequest = null
      try {
        this.currentRequest = await getInferenceRequest(id)
        return this.currentRequest
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to fetch request'
        throw e
      } finally {
        this.loading = false
      }
    },

    async deleteRequest(id: string) {
      const { deleteInferenceRequest } = useInferenceRequest()
      try {
        await deleteInferenceRequest(id)
        this.requests = this.requests.filter((r) => String(r.id) !== String(id))
        this.pagination.count = Math.max(0, this.pagination.count - 1)
        if (this.allRequests.some((r) => String(r.id) === String(id))) {
          this.allRequests = this.allRequests.filter((r) => String(r.id) !== String(id))
          this.allPagination.count = Math.max(0, this.allPagination.count - 1)
        }
        if (this.currentRequest && String(this.currentRequest.id) === String(id)) {
          this.currentRequest = null
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to delete request'
        throw e
      }
    },
  },
})