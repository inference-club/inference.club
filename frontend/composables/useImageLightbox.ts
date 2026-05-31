// Shared, app-wide image lightbox. A single <ImageLightbox /> is mounted in
// app.vue; anywhere can call open(url) to view an image full-screen.

export function useImageLightbox() {
  const current = useState<string | null>('image-lightbox', () => null)
  const open = (url?: string | null) => {
    if (url) current.value = url
  }
  const close = () => {
    current.value = null
  }
  return { current, open, close }
}
