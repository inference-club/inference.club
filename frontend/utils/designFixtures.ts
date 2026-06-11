import type { InferenceRequest } from '@/types'

// Deterministic mock data for the /design component gallery. Typed as the
// real InferenceRequest so API shape changes break the gallery loudly.
//
// Timestamps are fixed *offsets* from now, so relative labels ("2h ago")
// render identically across runs/days — which is what lets the gallery pages
// participate in pixel baselines (e2e/baselines.spec.ts).
//
// Media is inline data-URI SVG/WAV (no network, no seeded backend needed),
// except the GLB which loads from /design/cube.glb in public/.

const ago = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString()

const svg = (hue: number, label: string) =>
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">` +
      `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
      `<stop offset="0" stop-color="hsl(${hue},70%,55%)"/>` +
      `<stop offset="1" stop-color="hsl(${(hue + 60) % 360},70%,35%)"/>` +
      `</linearGradient></defs>` +
      `<rect width="512" height="512" fill="url(#g)"/>` +
      `<text x="50%" y="52%" font-family="sans-serif" font-size="40" fill="white" text-anchor="middle" opacity="0.85">${label}</text>` +
      `</svg>`,
  )

// 0.4s of silence as a riff-free WAV: header for 8-bit mono 8kHz + zeros.
const silentWav = (() => {
  const samples = 3200
  const header = [
    0x52, 0x49, 0x46, 0x46, ...le32(36 + samples), 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6d, 0x74, 0x20, ...le32(16), 1, 0, 1, 0, ...le32(8000), ...le32(8000),
    1, 0, 8, 0, 0x64, 0x61, 0x74, 0x61, ...le32(samples),
  ]
  const bytes = new Uint8Array(header.length + samples)
  bytes.set(header)
  bytes.fill(128, header.length)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return `data:audio/wav;base64,${btoa(bin)}`
})()

function le32(n: number): number[] {
  return [n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff]
}

const base = {
  status: 'PROCESSED' as const,
  provider: { id: 1, name: 'design-node' } as InferenceRequest['provider'],
  latency_ms: 1843,
  visibility: 'PUBLIC' as const,
  is_owner: true,
  owner: 'designbot',
  github_login: 'designbot',
  star_count: 3,
  is_starred: false,
  is_bookmarked: false,
  modified_on: ago(2),
}

export const fixtureRequests: Record<string, InferenceRequest> = {
  LLM: {
    ...base,
    id: 'fx-llm',
    inference_type: 'LLM',
    model_name: 'qwen3-30b-a3b-instruct',
    created_on: ago(2),
    streamed: true,
    has_reasoning: true,
    message_count: 4,
    usage: { prompt_tokens: 412, completion_tokens: 1289, total_tokens: 1701 },
    prompt_preview:
      'Explain the tradeoffs between serving media through an application server versus a public object-storage bucket with a CDN in front.',
    response_preview:
      'Serving media through the app couples bandwidth to your compute tier and adds latency, while a public bucket with immutable cache headers offloads bytes to edge infrastructure…',
  },
  STT: {
    ...base,
    id: 'fx-stt',
    inference_type: 'STT',
    model_name: 'whisper-large-v3',
    created_on: ago(5),
    audio_seconds: 12.4,
    audio_url: silentWav,
    response_preview:
      'Welcome back to the inference club podcast — today we are talking about running open models on hardware you own.',
  },
  TTS: {
    ...base,
    id: 'fx-tts',
    inference_type: 'TTS',
    model_name: 'kokoro-82m',
    created_on: ago(8),
    audio_seconds: 7.1,
    output_audio_url: silentWav,
    prompt_preview: 'The quick brown fox jumps over the lazy dog, twice, with feeling.',
  },
  MUSIC: {
    ...base,
    id: 'fx-music',
    inference_type: 'MUSIC',
    model_name: 'ace-step-v1-3.5b',
    created_on: ago(12),
    audio_seconds: 92.0,
    output_audio_url: silentWav,
    prompt_preview: 'Dreamy synthwave with a steady kick, warm pads, and a hopeful arpeggio that builds.',
  },
  IMAGE: {
    ...base,
    id: 'fx-image',
    inference_type: 'IMAGE',
    model_name: 'flux.1-schnell',
    created_on: ago(20),
    image_count: 4,
    image_urls: [svg(210, '1'), svg(280, '2'), svg(330, '3'), svg(30, '4')],
    prompt_preview: 'Isometric illustration of a tiny datacenter inside a terrarium, soft volumetric light.',
  },
  MESH: {
    ...base,
    id: 'fx-mesh',
    inference_type: 'MESH',
    model_name: 'trellis-2',
    created_on: ago(30),
    model_url: '/design/cube.glb',
    input_image_url: svg(120, 'in'),
    mesh: { seed: 42, vertices: 15234, faces: 30168 },
    prompt_preview: 'in.png',
  },
  VIDEO: {
    ...base,
    id: 'fx-video',
    inference_type: 'VIDEO',
    model_name: 'ltx-2',
    created_on: ago(40),
    video_url: '', // gallery renders the poster/empty state; sweeps cover real video
    input_image_url: svg(0, 'frame'),
    video: { seconds: 6, width: 1216, height: 704, fps: 24 },
    audio_seconds: 6,
    prompt_preview: 'A paper boat drifting down a rain gutter, cinematic, shallow depth of field.',
  },
}

// The side-scroll torture tests: unbroken tokens and URLs at the lengths
// that historically broke mobile. If these render without horizontal
// overflow, real content will too.
const LONG_TOKEN = 'Z'.repeat(120)
const LONG_URL =
  'https://example.com/extremely/long/path/that/never/breaks/' + 'segment/'.repeat(18) + 'end'

export const worstCaseRequests: InferenceRequest[] = [
  {
    ...fixtureRequests.LLM,
    id: 'fx-worst-llm',
    model_name: 'super-extremely-long-model-name-that-overflows-badges-v2.5-instruct-32k-awq',
    prompt_preview: `${LONG_TOKEN} ${LONG_URL}`,
    response_preview: LONG_URL + '?query=' + 'param'.repeat(40),
  },
  {
    ...fixtureRequests.MUSIC,
    id: 'fx-worst-music',
    prompt_preview: 'hyperpop'.repeat(30),
  },
]
