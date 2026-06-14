// Shared, app-wide image lightbox. A single <ImageLightbox /> is mounted in
// app.vue; anywhere can call open(url) or openList(urls, index) to view images.

export function useImageLightbox() {
  const current = useState<string | null>('image-lightbox', () => null)
  const list = useState<string[]>('image-lightbox-list', () => [])
  const index = useState<number>('image-lightbox-index', () => 0)

  const open = (url?: string | null) => {
    if (url) {
      list.value = []
      index.value = 0
      current.value = url
    }
  }

  const openList = (urls: string[], startIndex = 0) => {
    if (urls.length === 0) return
    list.value = urls
    index.value = startIndex
    current.value = urls[startIndex]
  }

  const prev = () => {
    if (list.value.length < 2) return
    index.value = (index.value - 1 + list.value.length) % list.value.length
    current.value = list.value[index.value]
  }

  const next = () => {
    if (list.value.length < 2) return
    index.value = (index.value + 1) % list.value.length
    current.value = list.value[index.value]
  }

  const close = () => {
    current.value = null
    list.value = []
    index.value = 0
  }

  const hasNav = computed(() => list.value.length > 1)

  return { current, list, index, open, openList, prev, next, close, hasNav }
}
