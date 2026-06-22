// Continuous "call-style" playback for a voice conversation: play a single
// message's audio, or start from one message and auto-advance through every
// following message (user recording → AI reply → next…). Used by the live Voice
// Agent page and the saved-session viewer.
//
// Each message exposes ordered audio clips as `audio: { url }[]` (a user turn
// has one mic recording; an assistant turn has one clip per spoken paragraph).
// Clip URLs are MediaAsset routes; we fetch them WITH credentials (owner-gated
// INPUT_AUDIO needs the session cookie, and this works cross-origin in dev) and
// play via object URLs. `blob:` URLs (a live, in-session clip) are used as-is.
import { ref, type Ref } from 'vue'

export interface PlayableMessage {
  audio?: { url: string }[]
}

export function useConversationPlayer(opts: { rate?: Ref<number> } = {}) {
  const activeMsg = ref<number | null>(null) // which message is currently sounding
  const playing = ref(false)
  const paused = ref(false)

  let audioEl: HTMLAudioElement | null = null
  let queue: { msg: number; url: string }[] = []
  let qi = 0
  let token = 0 // invalidates in-flight async work when stop()/new play starts
  const cache = new Map<string, string>() // assetUrl → object URL
  const objectUrls = new Set<string>()

  const resolve = async (url: string): Promise<string> => {
    if (url.startsWith('blob:')) return url
    const hit = cache.get(url)
    if (hit) return hit
    const res = await fetch(url, { credentials: 'include' })
    if (!res.ok) throw new Error(`audio ${res.status}`)
    const obj = URL.createObjectURL(await res.blob())
    cache.set(url, obj)
    objectUrls.add(obj)
    return obj
  }

  const teardown = () => {
    if (audioEl) {
      audioEl.pause()
      audioEl.onended = null
      audioEl.onerror = null
      audioEl = null
    }
  }

  const stop = () => {
    token++
    teardown()
    queue = []
    qi = 0
    activeMsg.value = null
    playing.value = false
    paused.value = false
  }

  const playNext = async (my: number) => {
    if (my !== token) return
    if (qi >= queue.length) {
      teardown()
      activeMsg.value = null
      playing.value = false
      return
    }
    const item = queue[qi]
    activeMsg.value = item.msg
    let src: string
    try {
      src = await resolve(item.url)
    } catch {
      qi++
      return playNext(my) // skip a clip that won't load
    }
    if (my !== token) return
    teardown()
    audioEl = new Audio(src)
    if (opts.rate) audioEl.playbackRate = opts.rate.value
    audioEl.onended = () => { qi++; void playNext(my) }
    audioEl.onerror = () => { qi++; void playNext(my) }
    playing.value = true
    paused.value = false
    await audioEl.play().catch(() => { qi++; void playNext(my) })
  }

  // Build a clip queue from message `from` to `to` (inclusive) and start.
  const start = async (messages: PlayableMessage[], from: number, to: number) => {
    stop()
    const my = token
    queue = []
    for (let i = from; i <= to && i < messages.length; i++) {
      for (const c of messages[i]?.audio || []) queue.push({ msg: i, url: c.url })
    }
    qi = 0
    if (!queue.length) return
    await playNext(my)
  }

  // Play a single message's clips.
  const playOne = (messages: PlayableMessage[], i: number) => start(messages, i, i)
  // Play from message i through the end (call-style auto-advance).
  const playFrom = (messages: PlayableMessage[], i: number) => start(messages, i, messages.length - 1)
  const playAll = (messages: PlayableMessage[]) => start(messages, 0, messages.length - 1)

  const pause = () => {
    if (audioEl && playing.value && !paused.value) {
      audioEl.pause()
      paused.value = true
    }
  }
  const resume = () => {
    if (audioEl && paused.value) {
      void audioEl.play()
      paused.value = false
    }
  }

  // Live rate change for the currently-playing clip.
  const setRate = (r: number) => { if (audioEl) audioEl.playbackRate = r }

  const dispose = () => {
    stop()
    objectUrls.forEach((u) => URL.revokeObjectURL(u))
    objectUrls.clear()
    cache.clear()
  }

  return { activeMsg, playing, paused, playOne, playFrom, playAll, pause, resume, stop, setRate, dispose }
}
