// Mock Living Cluster data for /design/cluster — a frozen, deterministic copy
// of Brian's real home fleet (a1/a2/a3/spark + the LM Studio satellite),
// captured from the dev backend on 2026-06-12. The design page renders the
// scene from this snapshot so the viz can be art-directed without a live
// agent. Activity buckets are fabricated (the real hour was idle) but shaped
// like plausible traffic so pulses and sparklines have something to say.

import type { ParsedManifest } from '@/composables/useManifest'
import {
  buildClusterSnapshot,
  type ClusterActivityPayload,
  type ClusterSnapshot,
  type ClusterStatePayload,
  type ServiceActivity,
} from '@/composables/useClusterState'

export type MockScenario = 'live' | 'degraded' | 'manifest'

const MANIFEST: ParsedManifest = {
  schema_version: 1,
  discovery: 'kubernetes',
  agent: { name: 'club-host-k8s' },
  hosts: [
    {
      id: 'a1',
      hostname: 'a1',
      address: '192.168.5.253',
      gpu: { count: 1, vendor: 'nvidia' },
      services: [
        {
          name: 'magpie-tts',
          type: 'tts',
          engine: 'other',
          url: 'http://magpie-tts.inference-club.svc.cluster.local:9000/v1',
          models: [{ id: 'magpie-tts-multilingual' }],
          command: 'nvcr.io/nim/nvidia/magpie-tts-multilingual:latest',
        },
      ],
    },
    {
      id: 'a2',
      hostname: 'a2',
      address: '192.168.5.96',
      gpu: { count: 1, vendor: 'nvidia' },
      services: [
        {
          name: 'flux2-klein',
          type: 'image',
          engine: 'other',
          url: 'http://flux2-klein.inference-club.svc.cluster.local:8000/v1',
          models: [{ id: 'flux-2-klein' }],
          command: 'ghcr.io/inference-club/flux2-klein:v0.1',
        },
      ],
    },
    {
      id: 'a3',
      hostname: 'a3',
      address: '192.168.5.173',
      gpu: { count: 1, vendor: 'nvidia' },
      services: [
        {
          name: 'ltx2',
          type: 'video',
          engine: 'other',
          url: 'http://ltx2.inference-club.svc.cluster.local:8023',
          models: [{ id: 'ltx-2' }],
          command: 'ghcr.io/inference-club/ltx2-server:v0.1 uvicorn ltx_server.app:app --host 0.0.0.0 --port 8023',
        },
      ],
    },
    {
      id: 'external-lmstudio',
      address: '192.168.6.19',
      notes: 'external endpoint (outside the cluster)',
      services: [
        {
          name: 'lmstudio',
          type: 'llm',
          engine: 'lmstudio',
          url: 'http://lmstudio.inference-club.svc.cluster.local:1234/v1',
          models: [{ id: 'google/gemma-4-12b', hf: 'google/gemma-4-12B' }],
        },
      ],
    },
    {
      id: 'spark',
      hostname: 'spark-d2ce',
      address: '192.168.6.19',
      gpu: { count: 1, vendor: 'nvidia' },
      services: [
        {
          name: 'acestep',
          type: 'music',
          engine: 'other',
          url: 'http://acestep.inference-club.svc.cluster.local:8015',
          models: [{ id: 'acestep-v15-turbo' }],
          command: 'ghcr.io/inference-club/acestep:v1.5-spark-arm64-r3',
        },
        {
          name: 'nemotron-asr',
          type: 'stt',
          engine: 'other',
          url: 'http://nemotron-asr.inference-club.svc.cluster.local:8105/v1',
          models: [{ id: 'nvidia/nemotron-3.5-asr-streaming-0.6b', hf: 'nvidia/nemotron-3.5-asr-streaming-0.6b' }],
          command: 'ghcr.io/inference-club/nemotron-asr:latest-spark-arm64',
        },
        {
          name: 'trellis2',
          type: 'mesh',
          engine: 'other',
          url: 'http://trellis2.inference-club.svc.cluster.local:8000',
          models: [{ id: 'trellis-2' }],
          command: 'ghcr.io/inference-club/trellis2:spark-arm64',
        },
      ],
    },
  ],
}

const HEALTHY_CONDITIONS = [
  { type: 'MemoryPressure', status: 'False', reason: 'KubeletHasSufficientMemory' },
  { type: 'DiskPressure', status: 'False', reason: 'KubeletHasNoDiskPressure' },
  { type: 'PIDPressure', status: 'False', reason: 'KubeletHasSufficientPID' },
  { type: 'Ready', status: 'True', reason: 'KubeletReady' },
]

function liveState(scenario: MockScenario): ClusterStatePayload {
  const degraded = scenario === 'degraded'
  return {
    discovery: 'kubernetes',
    collected_at: new Date().toISOString(),
    metrics_available: true,
    nodes: [
      {
        name: 'a1', host_id: 'a1', ready: true, conditions: HEALTHY_CONDITIONS,
        architecture: 'amd64', kubelet_version: 'v1.35.5+k3s1', os_image: 'Ubuntu 24.04.4 LTS',
        memory: { allocatable_bytes: 16688115712, capacity_bytes: 16688115712, usage_bytes: 8448741376 },
        gpu_allocatable: 1,
        // a1 runs dcgm-exporter — a busy 4090 (~17/24 GiB, 55% util).
        gpu: {
          vram_used_bytes: 18253611008, vram_total_bytes: 25769803776, util_percent: 55,
          devices: [{ index: 0, model: 'NVIDIA GeForce RTX 4090', vram_used_bytes: 18253611008, vram_total_bytes: 25769803776, util_percent: 55 }],
        },
      },
      {
        name: 'a2', host_id: 'a2', ready: true, conditions: HEALTHY_CONDITIONS,
        architecture: 'amd64', kubelet_version: 'v1.35.5+k3s1', os_image: 'Ubuntu 24.04.4 LTS',
        memory: { allocatable_bytes: 67147755520, capacity_bytes: 67147755520, usage_bytes: 15806873600 },
        gpu_allocatable: 1,
      },
      {
        name: 'a3', host_id: 'a3', ready: !degraded,
        conditions: degraded
          ? [{ type: 'Ready', status: 'False', reason: 'KubeletNotReady' }]
          : HEALTHY_CONDITIONS,
        architecture: 'amd64', kubelet_version: 'v1.35.5+k3s1', os_image: 'Ubuntu 24.04.4 LTS',
        memory: { allocatable_bytes: 67146694656, capacity_bytes: 67146694656, usage_bytes: degraded ? 0 : 18775068672 },
        gpu_allocatable: 1,
        // a3 runs dcgm-exporter too — a lightly-loaded 4090 (~12/24 GiB, 30% util).
        gpu: {
          vram_used_bytes: 12884901888, vram_total_bytes: 25769803776, util_percent: 30,
          devices: [{ index: 0, model: 'NVIDIA GeForce RTX 4090', vram_used_bytes: 12884901888, vram_total_bytes: 25769803776, util_percent: 30 }],
        },
      },
      {
        name: 'spark-d2ce', host_id: 'spark', ready: true, conditions: HEALTHY_CONDITIONS,
        architecture: 'arm64', kubelet_version: 'v1.35.5+k3s1', os_image: 'Ubuntu 24.04.4 LTS',
        memory: { allocatable_bytes: 130663591936, capacity_bytes: 130663591936, usage_bytes: 47096365056 },
        gpu_allocatable: 1,
      },
    ],
    pods: [
      { name: 'magpie-tts-86bd569b5c-mzs2t', service: 'magpie-tts', node: 'a1', host_id: 'a1', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 7436365824 },
      { name: 'flux2-klein-6fd6b79887-ksfcd', service: 'flux2-klein', node: 'a2', host_id: 'a2', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 12148899840 },
      degraded
        ? { name: 'ltx2-79d9cbc956-pb8cs', service: 'ltx2', node: 'a3', host_id: 'a3', phase: 'Unknown', ready: false, restarts: 3, memory_usage_bytes: 0 }
        : { name: 'ltx2-79d9cbc956-pb8cs', service: 'ltx2', node: 'a3', host_id: 'a3', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 16496300032 },
      { name: 'acestep-586468c6b5-wdcxx', service: 'acestep', node: 'spark-d2ce', host_id: 'spark', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 657006592 },
      { name: 'nemotron-asr-54d45b7f48-dqz29', service: 'nemotron-asr', node: 'spark-d2ce', host_id: 'spark', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 2685136896 },
      degraded
        ? { name: 'trellis2-cdd79d6d8-hw6m6', service: 'trellis2', node: 'spark-d2ce', host_id: 'spark', phase: 'Running', ready: false, restarts: 14, reason: 'CrashLoopBackOff', memory_usage_bytes: 812340224 }
        : { name: 'trellis2-cdd79d6d8-hw6m6', service: 'trellis2', node: 'spark-d2ce', host_id: 'spark', phase: 'Running', ready: true, restarts: 0, memory_usage_bytes: 24792530944 },
    ],
  }
}

// Deterministic per-minute buckets: a base rate shaped by two sines plus
// hand-placed bursts, so each service's sparkline has character without RNG.
function buckets(base: number, amp: number, phase: number, bursts: Record<number, number> = {}): number[] {
  const out: number[] = []
  for (let i = 0; i < 60; i++) {
    const wave = base + amp * (0.5 + 0.5 * Math.sin(i / 6 + phase)) * Math.sin(i / 2.1 + phase * 2)
    out.push(Math.max(0, Math.round(wave)) + (bursts[i] ?? 0))
  }
  return out
}

function activity(scenario: MockScenario): ClusterActivityPayload | null {
  if (scenario === 'manifest') return null
  // Tails (indexes 55–59) run hot so the live view has visible pulse traffic.
  const services: ServiceActivity[] = [
    { service: 'lmstudio', total: 0, last_request_at: null, buckets: buckets(1.4, 1.6, 0.3, { 55: 4, 56: 3, 57: 5, 58: 6, 59: 4 }) },
    { service: 'flux2-klein', total: 0, last_request_at: null, buckets: buckets(0.7, 1.8, 1.7, { 30: 4, 31: 6, 32: 3, 55: 5, 56: 7, 57: 6, 58: 8, 59: 7 }) },
    { service: 'magpie-tts', total: 0, last_request_at: null, buckets: buckets(0.4, 1.1, 3.1, { 44: 3, 56: 2, 57: 3, 58: 4, 59: 3 }) },
    { service: 'nemotron-asr', total: 0, last_request_at: null, buckets: buckets(0.3, 0.9, 4.4, { 12: 2, 45: 2, 57: 2, 58: 2, 59: 2 }) },
    { service: 'ltx2', total: 0, last_request_at: null, buckets: buckets(0, 0.4, 2.2, { 18: 1, 38: 1, 56: 1, 58: 1, 59: 1 }) },
    { service: 'acestep', total: 0, last_request_at: null, buckets: buckets(0, 0.3, 5.0, { 25: 1, 52: 1, 57: 1, 59: 1 }) },
    { service: 'trellis2', total: 0, last_request_at: null, buckets: buckets(0, 0.5, 0.9, { 6: 2, 7: 3, 8: 1, 56: 1, 58: 2, 59: 1 }) },
  ]
  if (scenario === 'degraded') {
    // a3 is down — video traffic flatlines mid-window.
    const ltx = services.find(s => s.service === 'ltx2')!
    ltx.buckets = ltx.buckets.map((v, i) => (i > 35 ? 0 : v))
  }
  for (const s of services) {
    s.total = s.buckets.reduce((a, b) => a + b, 0)
    s.last_request_at = s.total > 0 ? new Date().toISOString() : null
  }
  return {
    window_minutes: 60,
    bucket_seconds: 60,
    generated_at: new Date().toISOString(),
    services,
  }
}

export function buildMockClusterSnapshot(scenario: MockScenario = 'live'): ClusterSnapshot {
  const live = scenario === 'manifest' ? null : liveState(scenario)
  return buildClusterSnapshot(MANIFEST, live, activity(scenario))!
}
