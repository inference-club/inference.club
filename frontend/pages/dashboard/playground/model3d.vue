<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Box, Clock, Dices, ExternalLink, Loader2, Shapes, Sparkles, Square, Upload, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMeshGeneration, type MeshResult } from '@/composables/useMeshGeneration'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const { listMeshModels, generate } = useMeshGeneration()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// Required source image.
interface SourceImage { blob: Blob; name: string; url: string }
const source = ref<SourceImage | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const MAX_MB = 25

// Options — resolution + seed (per product decision).
const RESOLUTIONS = [
  { value: '512', label: '512 · fast' },
  { value: '1024', label: '1024 · balanced' },
  { value: '1536', label: '1536 · sharpest' },
]
const resolution = ref('512')
const seed = ref(42)
const randomizeSeed = ref(false)

const running = ref(false)
let controller: AbortController | null = null

interface ResultRow {
  id: string
  sourceUrl: string
  result: MeshResult
  latencyMs: number
  model: string
}
const results = ref<ResultRow[]>([])

const uid = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.round(Math.random() * 1e9)}`

const setSource = (blob: Blob, name: string) => {
  if (blob.size > MAX_MB * 1024 * 1024) {
    toast.error(t('model3d.tooLarge', { mb: MAX_MB }))
    return
  }
  if (source.value) URL.revokeObjectURL(source.value.url)
  source.value = { blob, name, url: URL.createObjectURL(blob) }
}
const onFiles = (e: Event) => {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setSource(f, f.name)
  if (fileInput.value) fileInput.value.value = ''
}
const onDrop = (e: DragEvent) => {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  if (!f.type.startsWith('image/')) return toast.error(t('model3d.dropImage'))
  setSource(f, f.name)
}
const clearSource = () => {
  if (source.value) URL.revokeObjectURL(source.value.url)
  source.value = null
}

const canRun = computed(() => !!model.value && !!source.value && !running.value)

const run = async () => {
  if (!canRun.value || !source.value) return
  running.value = true
  controller = new AbortController()
  const start = performance.now()
  const src = source.value
  try {
    const result = await generate(
      src.blob,
      src.name,
      model.value,
      {
        resolution: resolution.value,
        ...(randomizeSeed.value ? { randomize_seed: true } : { seed: seed.value }),
      },
      controller.signal,
    )
    results.value.unshift({
      id: uid(),
      sourceUrl: URL.createObjectURL(src.blob),
      result,
      latencyMs: Math.round(performance.now() - start),
      model: model.value,
    })
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || t('model3d.failed'))
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

onMounted(async () => {
  try {
    models.value = await listMeshModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
    } else {
      modelsError.value = t('model3d.noModels')
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || t('model3d.loadFailed')
  } finally {
    loadingModels.value = false
  }
})

onBeforeUnmount(() => {
  if (source.value) URL.revokeObjectURL(source.value.url)
  results.value.forEach((r) => URL.revokeObjectURL(r.sourceUrl))
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-5xl">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Shapes class="h-6 w-6" /> {{ t('model3d.title') }}
        </h1>
        <p class="text-sm text-muted-foreground mt-1">{{ t('model3d.subtitle') }}</p>
      </div>
      <Select v-model="model" :disabled="loadingModels || !models.length">
        <SelectTrigger class="w-[18rem] font-mono text-xs">
          <SelectValue :placeholder="loadingModels ? t('model3d.loadingModels') : t('model3d.selectModel')" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="m in models" :key="m.id" :value="m.id" class="font-mono text-xs">
            {{ m.id }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-muted text-muted-foreground rounded text-sm">
      {{ modelsError }}
    </div>

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_16rem] gap-4 items-start">
      <!-- Composer -->
      <div class="space-y-3">
        <Card class="p-4 space-y-3">
          <!-- Source image (required) -->
          <div
            class="rounded-xl border border-dashed transition-colors p-4 text-center text-sm"
            :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div v-if="source" class="flex items-center gap-3">
              <img :src="source.url" class="size-16 rounded object-cover border" />
              <span class="text-xs text-muted-foreground flex-1 text-left truncate">
                {{ t('model3d.willConvert') }} <strong>{{ source.name }}</strong>
              </span>
              <Button variant="ghost" size="icon" @click="clearSource"><X class="size-4" /></Button>
            </div>
            <div v-else class="text-muted-foreground py-2">
              <Upload class="size-5 inline mr-1 opacity-60" />
              {{ t('model3d.dropPrompt') }}
              <button class="text-primary underline" @click="fileInput?.click()">{{ t('model3d.browse') }}</button>
            </div>
            <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFiles" />
          </div>

          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ t('model3d.timingHint') }}</span>
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> {{ t('model3d.stop') }}
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component :is="running ? Loader2 : Sparkles" class="size-4" :class="running ? 'animate-spin' : ''" />
                {{ t('model3d.generate') }}
              </Button>
            </div>
          </div>
        </Card>

        <!-- In-flight notice (generation is slow) -->
        <Card v-if="running" class="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 class="size-4 animate-spin" /> {{ t('model3d.generating') }}
        </Card>

        <!-- Results -->
        <Card v-for="r in results" :key="r.id" class="p-4 space-y-3">
          <div class="flex items-center gap-2 flex-wrap text-[11px] text-muted-foreground">
            <Badge variant="outline" class="font-mono">{{ r.model }}</Badge>
            <span class="inline-flex items-center gap-1"><Clock class="size-3" /> {{ r.latencyMs }} ms</span>
            <span v-if="r.result.metadata?.vertices" class="inline-flex items-center gap-1">
              <Box class="size-3" /> {{ r.result.metadata.vertices.toLocaleString() }} verts
            </span>
            <NuxtLink
              v-if="r.result.requestId"
              :to="`/dashboard/inference/requests/${r.result.requestId}`"
              class="ml-auto inline-flex items-center gap-1 underline hover:text-foreground"
            >
              {{ t('model3d.openDetail') }} <ExternalLink class="size-3" />
            </NuxtLink>
          </div>
          <ModelViewer
            v-if="r.result.url"
            :src="r.result.url"
            :poster-src="r.sourceUrl"
            alt="Generated 3D model"
          />
        </Card>
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {{ t('model3d.options') }}
        </Label>
        <div>
          <Label class="text-xs text-muted-foreground">{{ t('model3d.resolution') }}</Label>
          <Select v-model="resolution">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="r in RESOLUTIONS" :key="r.value" :value="r.value" class="text-sm">
                {{ r.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <div class="flex items-center justify-between">
            <Label class="text-xs text-muted-foreground">{{ t('model3d.seed') }}</Label>
            <button
              type="button"
              class="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              :class="randomizeSeed ? 'text-primary' : ''"
              @click="randomizeSeed = !randomizeSeed"
            >
              <Dices class="size-3.5" /> {{ t('model3d.randomize') }}
            </button>
          </div>
          <Input
            v-model.number="seed"
            type="number"
            :disabled="randomizeSeed"
            class="mt-1 h-8 text-sm tabular-nums"
            :class="randomizeSeed ? 'opacity-50' : ''"
          />
        </div>
        <p class="text-[11px] text-muted-foreground">{{ t('model3d.note') }}</p>
      </Card>
    </div>
  </div>
</template>
