<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Dices, Images, Loader2, Shapes, Sparkles, Square, Upload, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMeshGeneration } from '@/composables/useMeshGeneration'
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

// Bumped after each successful generation so the recent-for-this-model strip
// refetches and flashes the model that just finished.
const refreshKey = ref(0)

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

// Pick an existing inference.club image (recent / starred / bookmarked /
// collection / public search) as the source instead of uploading a file.
const pickerOpen = ref(false)
const onPickImage = ({ blob, name }: { blob: Blob; name: string }) => {
  setSource(blob, name)
}

const canRun = computed(() => !!model.value && !!source.value && !running.value)

const run = async () => {
  if (!canRun.value || !source.value) return
  running.value = true
  controller = new AbortController()
  const src = source.value
  try {
    await generate(
      src.blob,
      src.name,
      model.value,
      {
        resolution: resolution.value,
        ...(randomizeSeed.value ? { randomize_seed: true } : { seed: seed.value }),
      },
      controller.signal,
    )
    refreshKey.value++
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
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
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

          <!-- Or pick an existing image from the network -->
          <Button variant="outline" size="sm" class="w-full gap-2" @click="pickerOpen = true">
            <Images class="size-4" /> {{ t('model3d.picker.trigger') }}
          </Button>

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
          <Loader2 class="size-4 animate-spin shrink-0" />
          <span class="flex-1">{{ t('model3d.generating') }}</span>
          <ElapsedTimer :running="running" class="shrink-0 font-medium text-foreground" />
        </Card>

        <!-- Recent models for this model (the just-finished one flashes in) -->
        <RecentGenerations :model="model" type="MESH" :refresh-key="refreshKey" :title="t('model3d.recentTitle')" />
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

    <ImageSourcePicker v-model:open="pickerOpen" @select="onPickImage" />
  </div>
</template>
