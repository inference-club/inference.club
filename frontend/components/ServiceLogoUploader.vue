<script setup lang="ts">
// Owner-only logo control for a service: shows the current logo (or the engine
// glyph as fallback) with a hover affordance to upload/replace, and a small
// remove button when a custom logo is set. Self-contained — it owns the
// displayed logo state and emits changes so the parent can stay in sync.
import { Upload, X } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useServiceLogo } from '@/composables/useServiceLogo'

const props = withDefaults(
  defineProps<{
    serviceId: number
    engine: string
    logoUrl?: string | null
    size?: number
  }>(),
  { logoUrl: null, size: 30 },
)

const emit = defineEmits<{ (e: 'update:logoUrl', url: string | null): void }>()

const { upload, remove } = useServiceLogo()
const current = ref<string | null>(props.logoUrl)
watch(() => props.logoUrl, (v) => { current.value = v ?? null })

const fileInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)

const pick = () => fileInput.value?.click()

const onFile = async (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  try {
    const url = await upload(props.serviceId, file)
    current.value = url
    emit('update:logoUrl', url)
    toast.success('Logo updated')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Logo upload failed')
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

const onRemove = async () => {
  busy.value = true
  try {
    await remove(props.serviceId)
    current.value = null
    emit('update:logoUrl', null)
    toast.success('Logo removed')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Could not remove logo')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="group/logo relative inline-flex">
    <EngineLogo :engine="engine" :logo-url="current" :size="size" />
    <!-- upload/replace overlay -->
    <button
      type="button"
      class="absolute inset-0 flex items-center justify-center rounded-[7px] bg-black/55 text-white opacity-0 transition-opacity group-hover/logo:opacity-100 disabled:opacity-100"
      :disabled="busy"
      :title="current ? 'Replace logo' : 'Upload logo'"
      @click="pick"
    >
      <Upload class="size-3.5" :class="busy ? 'animate-pulse' : ''" />
    </button>
    <!-- remove (only when a custom logo is set) -->
    <button
      v-if="current && !busy"
      type="button"
      class="absolute -right-1.5 -top-1.5 hidden size-4 items-center justify-center rounded-full bg-destructive text-destructive-foreground group-hover/logo:flex"
      title="Remove logo"
      @click="onRemove"
    >
      <X class="size-2.5" />
    </button>
    <input
      ref="fileInput"
      type="file"
      accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
      class="hidden"
      @change="onFile"
    >
  </div>
</template>
