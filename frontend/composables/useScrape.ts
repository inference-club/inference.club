// Client for the web-scrape playground (PRD 12). Talks to the OpenAI-style
// /v1/scrape endpoint with the logged-in session (no API key to paste), and
// lists the `scrape`-type models the user can route to.

export interface ScrapeResult {
  request_id: string
  markdown: string
  title: string
  source_url: string
  doc_asset_id: number | null
  chars: number
}

export function useScrape() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const listScrapeModels = async (): Promise<string[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, {
      credentials: 'include',
    })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? [])
      .filter((m: { service_type?: string }) => m.service_type === 'scrape')
      .map((m: { id: string }) => m.id)
  }

  const scrape = async (
    url: string,
    model: string,
    signal?: AbortSignal,
  ): Promise<ScrapeResult> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/scrape`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({ url, model }),
      signal,
    })
    if (!res.ok) {
      let msg = `Request failed (HTTP ${res.status})`
      try {
        const e = await res.json()
        msg = e?.error?.message || msg
      } catch {
        // keep the generic message
      }
      throw new Error(msg)
    }
    return (await res.json()) as ScrapeResult
  }

  return { listScrapeModels, scrape }
}
