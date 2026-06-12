<script setup lang="ts">
// Living Cluster asset pipeline (PRD 07 V2, staff/dev) — the dogfooding loop:
// generate the cluster scene's chassis meshes through inference.club's OWN
// modalities. Per form factor: a curated prompt → FLUX image
// (/v1/images/generations) → TRELLIS GLB (/v1/3d/generations) → preview →
// a ready-to-commit assets.json entry carrying the generation request's
// attribution. Every run is an ordinary InferenceRequest, so the feature
// doubles as a standing integration test of both modalities.
//
// Persistence is deliberately git: copy the emitted JSON into
// public/design/cluster/assets.json and commit. Generated assets stay
// versioned, attributed, and reviewable like any other change.
import { Boxes, Copy, Image as ImageIcon, Loader2, Wand2 } from 'lucide-vue-next'
import { useImageGeneration, type GeneratedImage } from '@/composables/useImageGeneration'
import { useMeshGeneration, type MeshResult } from '@/composables/useMeshGeneration'
import type { ModelInfo } from '@/composables/usePlayground'
import type { ClusterAssetEntry } from '@/composables/useClusterAssets'
import type { HostFormFactor } from '@/composables/useClusterState'

definePageMeta({ layout: 'app', middleware: 'staff' })
useHead({ title: 'Cluster assets — design' })

interface AssetSlot {
  key: HostFormFactor
  title: string
  prompt: string
  images: GeneratedImage[]
  chosenImage: string | null
  mesh: MeshResult | null
  busy: 'image' | 'mesh' | null
  error: string | null
}

// Curated prompts: white-background product shots convert cleanly to meshes
// (TRELLIS segments the subject; busy backgrounds bleed into the geometry).
const slots = reactive<AssetSlot[]>([
  {
    key: 'tower',
    title: 'Tower (GPU box)',
    prompt:
      'studio product photo of a black mid-tower gaming PC with a tempered glass side panel showing a large triple-fan GPU with glowing green accents, three-quarter view, plain white background, soft studio lighting',
    images: [], chosenImage: null, mesh: null, busy: null, error: null,
  },
  {
    key: 'slab',
    title: 'Slab (DGX Spark)',
    prompt:
      'studio product photo of a compact champagne-gold mini supercomputer, low flat rectangular chassis with a fine metallic mesh front, three-quarter view, plain white background, soft studio lighting',
    images: [], chosenImage: null, mesh: null, busy: null, error: null,
  },
  {
    key: 'box',
    title: 'Box (generic node)',
    prompt:
      'studio product photo of a plain dark-gray small-form-factor server cube with subtle ventilation slots and a single power LED, three-quarter view, plain white background, soft studio lighting',
    images: [], chosenImage: null, mesh: null, busy: null, error: null,
  },
  {
    key: 'satellite',
    title: 'Satellite (external endpoint)',
    prompt:
      'studio product photo of a small white rounded desktop device, sleek minimal puck-like computer with a soft status light, three-quarter view, plain white background, soft studio lighting',
    images: [], chosenImage: null, mesh: null, busy: null, error: null,
  },
])

const { listImageModels, generate: generateImage } = useImageGeneration()
const { listMeshModels, generate: generateMesh } = useMeshGeneration()

const imageModels = ref<ModelInfo[]>([])
const meshModels = ref<ModelInfo[]>([])
const imageModel = ref('')
const meshModel = ref('')

onMounted(async () => {
  try {
    imageModels.value = await listImageModels()
    imageModel.value = imageModels.value[0]?.id ?? ''
  } catch { /* picker shows "none online" */ }
  try {
    meshModels.value = await listMeshModels()
    meshModel.value = meshModels.value[0]?.id ?? ''
  } catch { /* picker shows "none online" */ }
})

const makeImage = async (slot: AssetSlot) => {
  if (!imageModel.value) return
  slot.busy = 'image'
  slot.error = null
  try {
    slot.images = await generateImage({
      model: imageModel.value,
      prompt: slot.prompt,
      n: 2,
      size: '1024x1024',
    })
    slot.chosenImage = slot.images[0]?.url ?? null
  } catch (e) {
    slot.error = e instanceof Error ? e.message : 'image generation failed'
  } finally {
    slot.busy = null
  }
}

const makeMesh = async (slot: AssetSlot) => {
  if (!meshModel.value || !slot.chosenImage) return
  slot.busy = 'mesh'
  slot.error = null
  try {
    const blob = await fetch(slot.chosenImage).then((r) => {
      if (!r.ok) throw new Error(`fetch source image: HTTP ${r.status}`)
      return r.blob()
    })
    slot.mesh = await generateMesh(blob, `cluster-${slot.key}.png`, meshModel.value, {
      randomize_seed: true,
    })
  } catch (e) {
    slot.error = e instanceof Error ? e.message : '3D generation failed'
  } finally {
    slot.busy = null
  }
}

// The ready-to-commit assets.json body, attributing each kept mesh to the
// generation request that produced it.
const snippet = computed(() => {
  const assets: Record<string, ClusterAssetEntry | null> = {}
  for (const slot of slots) {
    if (slot.mesh?.url) {
      assets[slot.key] = {
        url: slot.mesh.url,
        label: slot.title,
        request_id: slot.mesh.requestId || undefined,
        model: meshModel.value || undefined,
        seed: typeof slot.mesh.metadata?.seed === 'number' ? slot.mesh.metadata.seed : undefined,
        href: slot.mesh.requestId
          ? `/dashboard/inference/requests/${slot.mesh.requestId}`
          : undefined,
      }
    } else {
      assets[slot.key] = null
    }
  }
  return JSON.stringify({ version: 1, assets }, null, 2)
})

const copied = ref(false)
const copySnippet = async () => {
  await navigator.clipboard.writeText(snippet.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 1500)
}
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <div class="mb-6">
      <h1 class="flex items-center gap-2 text-2xl font-bold">
        <Boxes class="size-6 text-muted-foreground" /> Cluster assets
      </h1>
      <p class="mt-1 text-sm text-muted-foreground max-w-2xl">
        Generate the Living Cluster's chassis meshes through the platform's own
        modalities: prompt → image (<code class="text-foreground">/v1/images/generations</code>)
        → GLB (<code class="text-foreground">/v1/3d/generations</code>). Keep what you like,
        then commit the emitted JSON to
        <code class="text-foreground">public/design/cluster/assets.json</code> — the scene
        credits each machine to its generation request.
      </p>
    </div>

    <div class="mb-6 flex flex-wrap items-center gap-4 rounded-lg border bg-card p-3 text-sm">
      <label class="flex items-center gap-2">
        <ImageIcon class="size-4 text-muted-foreground" />
        <select v-model="imageModel" class="rounded-md border bg-background px-2 py-1.5">
          <option v-if="!imageModels.length" value="">no image models online</option>
          <option v-for="m in imageModels" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2">
        <Boxes class="size-4 text-muted-foreground" />
        <select v-model="meshModel" class="rounded-md border bg-background px-2 py-1.5">
          <option v-if="!meshModels.length" value="">no mesh models online</option>
          <option v-for="m in meshModels" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
      </label>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <section v-for="slot in slots" :key="slot.key" class="rounded-lg border bg-card p-4">
        <header class="mb-2 flex items-center justify-between">
          <h2 class="font-semibold">{{ slot.title }}</h2>
          <code class="text-xs text-muted-foreground">{{ slot.key }}</code>
        </header>

        <textarea
          v-model="slot.prompt"
          rows="3"
          class="w-full rounded-md border bg-background p-2 text-xs font-mono"
        />

        <div class="mt-2 flex flex-wrap gap-2">
          <button
            class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
            :disabled="!imageModel || slot.busy !== null"
            @click="makeImage(slot)"
          >
            <Loader2 v-if="slot.busy === 'image'" class="size-3.5 animate-spin" />
            <ImageIcon v-else class="size-3.5" />
            Generate image
          </button>
          <button
            class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
            :disabled="!meshModel || !slot.chosenImage || slot.busy !== null"
            @click="makeMesh(slot)"
          >
            <Loader2 v-if="slot.busy === 'mesh'" class="size-3.5 animate-spin" />
            <Wand2 v-else class="size-3.5" />
            Make 3D
          </button>
        </div>

        <p v-if="slot.error" class="mt-2 text-xs text-red-500">{{ slot.error }}</p>

        <div v-if="slot.images.length" class="mt-3 flex gap-2">
          <button
            v-for="img in slot.images"
            :key="img.url"
            class="relative size-24 overflow-hidden rounded-md border-2"
            :class="slot.chosenImage === img.url ? 'border-sky-500' : 'border-transparent'"
            @click="slot.chosenImage = img.url ?? null"
          >
            <img v-if="img.url" :src="img.url" class="size-full object-cover" alt="" />
          </button>
        </div>

        <div v-if="slot.mesh?.url" class="mt-3">
          <ModelViewer :src="slot.mesh.url" :downloadable="true" alt="Generated chassis" />
          <p class="mt-1 text-[11px] text-muted-foreground font-mono">
            request #{{ slot.mesh.requestId || '?' }}
            <template v-if="slot.mesh.metadata?.seed != null"> · seed {{ slot.mesh.metadata.seed }}</template>
          </p>
        </div>
      </section>
    </div>

    <section class="mt-8">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="font-semibold">assets.json</h2>
        <button
          class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
          @click="copySnippet"
        >
          <Copy class="size-3.5" /> {{ copied ? 'Copied!' : 'Copy' }}
        </button>
      </div>
      <pre class="overflow-x-auto rounded-lg border bg-muted/40 p-3 text-xs font-mono">{{ snippet }}</pre>
    </section>
  </div>
</template>
