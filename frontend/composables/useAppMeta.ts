// Build/version metadata from the backend (GET /api/meta/). Lets the UI show
// which build/environment it's talking to — the git-tag / image-tag surfaced
// by the deploy pipeline. Cached in shared state so the footer(s) fetch once.

export interface AppMeta {
  name: string
  version: string
  git_sha: string
  env: string
}

export function useAppMeta() {
  const config = useRuntimeConfig()
  const meta = useState<AppMeta | null>('appMeta', () => null)

  const load = async (): Promise<AppMeta | null> => {
    if (meta.value) return meta.value
    try {
      meta.value = await $fetch<AppMeta>(`${config.public.apiBase}/api/meta/`)
    } catch {
      // Non-fatal: the version chip simply won't render.
    }
    return meta.value
  }

  return { meta, load }
}
