// Thin wrapper around MediaRecorder for capturing microphone audio into a
// Blob. Shared by the chat playground (audio attachments) and the
// transcription playground.

import { ref } from 'vue'

export interface RecordedAudio {
  blob: Blob
  mime: string
  ext: string
}

export function useAudioRecorder() {
  const supported = ref(
    typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia &&
      typeof window !== 'undefined' &&
      'MediaRecorder' in window,
  )
  const recording = ref(false)

  let recorder: MediaRecorder | null = null
  let chunks: BlobPart[] = []
  let resolveStop: ((r: RecordedAudio) => void) | null = null
  let rejectStop: ((e: unknown) => void) | null = null

  const extFor = (mime: string) =>
    mime.includes('ogg') ? 'ogg' : mime.includes('wav') ? 'wav' : 'webm'

  // Starts recording. Returns a promise that resolves with the captured audio
  // once stop() is called.
  const start = async (): Promise<RecordedAudio> => {
    const media = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    recorder = new MediaRecorder(media)
    const promise = new Promise<RecordedAudio>((resolve, reject) => {
      resolveStop = resolve
      rejectStop = reject
    })
    recorder.ondataavailable = (ev) => {
      if (ev.data.size) chunks.push(ev.data)
    }
    recorder.onstop = () => {
      media.getTracks().forEach((t) => t.stop())
      const mime = recorder?.mimeType || 'audio/webm'
      const blob = new Blob(chunks, { type: mime })
      recording.value = false
      resolveStop?.({ blob, mime, ext: extFor(mime) })
    }
    recorder.onerror = (e) => {
      media.getTracks().forEach((t) => t.stop())
      recording.value = false
      rejectStop?.(e)
    }
    recorder.start()
    recording.value = true
    return promise
  }

  const stop = () => {
    if (recorder && recording.value) recorder.stop()
  }

  return { supported, recording, start, stop }
}
