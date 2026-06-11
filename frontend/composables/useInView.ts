import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * One-shot visibility flag: flips to true the first time `target` comes
 * within `rootMargin` of the viewport, then stops observing (media that has
 * started loading shouldn't unload when scrolled away). Used to defer media
 * fetches (audio/video metadata, posters) on list cards — native
 * loading="lazy" covers <img> but has no <audio>/<video> equivalent.
 *
 * False during SSR and until mounted, so server HTML carries no media URLs;
 * true immediately when IntersectionObserver is unavailable.
 */
export function useInView(target: Ref<HTMLElement | null>, rootMargin = '300px') {
  const inView = ref(false)
  let observer: IntersectionObserver | null = null

  onMounted(() => {
    const el = target.value
    if (!el || typeof IntersectionObserver === 'undefined') {
      inView.value = true
      return
    }
    observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          inView.value = true
          observer?.disconnect()
          observer = null
        }
      },
      { rootMargin },
    )
    observer.observe(el)
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return inView
}
