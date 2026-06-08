// Force a real file download in the browser, honoring the filename even when
// the asset is served from a different origin (our media lives on the API
// host, e.g. :8101, while the app runs on :3100). The HTML `download` attribute
// is ignored cross-origin, so we fetch the bytes into a blob and save that.

export function useFileDownload() {
  const downloading = ref(false)

  const download = async (url: string, filename: string) => {
    if (downloading.value) return
    downloading.value = true
    try {
      // Media assets are public-by-URL; include credentials so owner-gated
      // assets still work (CORS allows credentials for our origins).
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objectUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(objectUrl)
    } catch {
      // Last resort: open in a new tab so the user can still save it manually.
      window.open(url, '_blank')
    } finally {
      downloading.value = false
    }
  }

  return { downloading, download }
}
