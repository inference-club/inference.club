// Shared "Generate N" helper for the playground. Takes the same body a page
// would POST synchronously and instead enqueues `count` copies as async jobs
// (a single /v1/batches submission). The backend dispatcher runs them one at a
// time per provider/service capacity — so on a single-node setup they drain
// sequentially — and the user watches them on /dashboard/queue.
import { toast } from 'vue-sonner'
import { useAsyncJobs } from '@/composables/useAsyncJobs'

const MAX_QUEUE = 50

function statusOf(err: unknown): number | undefined {
  const e = err as {
    status?: number
    statusCode?: number
    response?: { status?: number }
  }
  return e?.status ?? e?.statusCode ?? e?.response?.status
}

function messageOf(err: unknown): string | undefined {
  const e = err as {
    data?: { error?: { message?: string } }
    message?: string
  }
  return e?.data?.error?.message || e?.message
}

export function useQueueGenerations() {
  const { enqueueBatch } = useAsyncJobs()
  // Captured in setup so the toast action can navigate later, outside context.
  const router = useRouter()

  /**
   * Queue `count` copies of one request. `label` is the singular noun used in
   * the toast ("image", "song", …). Returns true on success.
   */
  const queue = async (
    endpoint: string,
    body: Record<string, unknown>,
    count: number,
    label = 'request',
  ): Promise<boolean> => {
    const n = Math.max(1, Math.min(MAX_QUEUE, Math.floor(count) || 1))
    const requests = Array.from({ length: n }, () => ({ endpoint, body }))
    try {
      await enqueueBatch(requests, `${n} × ${label}`)
      toast.success(`Queued ${n} ${label}${n > 1 ? 's' : ''}`, {
        description: 'Processed one at a time as capacity frees up.',
        action: { label: 'View queue', onClick: () => router.push('/dashboard/queue') },
      })
      return true
    } catch (err: unknown) {
      if (statusOf(err) === 503) {
        toast.error('The async queue isn’t enabled on this server yet.')
      } else {
        toast.error(messageOf(err) || 'Could not queue requests')
      }
      return false
    }
  }

  return { queue }
}
