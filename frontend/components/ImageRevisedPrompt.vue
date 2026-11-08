<script setup lang="ts">
// What an image model actually rendered from, when the provider reports it:
// the `revised_prompt` (e.g. FLUX 3 Klein's prompt-upsampler caption), plus the
// resolved seed. Renders nothing for models that report neither. `meta` is the
// request API's `image` field (first image flattened, `images` when n > 1).
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

interface ImageOutputMeta {
  revised_prompt?: string
  upsampled?: boolean
  seed?: number
}
const props = defineProps<{ meta?: (ImageOutputMeta & { images?: ImageOutputMeta[] }) | null }>()

// One row per distinct revised prompt; a single row when every image shares it.
const rows = computed(() => {
  const m = props.meta
  if (!m) return []
  const all = m.images?.length ? m.images : [m]
  const seen = new Set<string>()
  return all
    .map((im, i) => ({ ...im, index: i }))
    .filter((im) => im.revised_prompt && !seen.has(im.revised_prompt) && seen.add(im.revised_prompt))
})
const multi = computed(() => (props.meta?.images?.length ?? 0) > 1)
const seeds = computed(() => {
  const m = props.meta
  if (!m) return []
  const all = m.images?.length ? m.images : [m]
  return all.map((im) => im.seed).filter((s): s is number => typeof s === 'number')
})

const expanded = ref(false)
const copied = ref<number | null>(null)
async function copy(text: string, index: number) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = index
    setTimeout(() => (copied.value = null), 1500)
  } catch {
    /* clipboard unavailable (insecure context) — ignore */
  }
}
</script>

<template>
  <div v-if="rows.length || seeds.length" class="text-sm space-y-2">
    <div v-for="row in rows" :key="row.index" class="rounded-md border bg-muted/40 p-3">
      <div class="mb-1 flex items-center justify-between gap-2">
        <span class="flex items-center gap-2 text-muted-foreground">
          {{ row.upsampled === false ? 'Revised prompt' : 'Upsampled prompt' }}
          <Badge v-if="multi" variant="outline">image {{ row.index + 1 }}</Badge>
        </span>
        <Button
          variant="ghost" size="sm" class="h-6 px-2 text-xs"
          @click="copy(row.revised_prompt!, row.index)"
        >
          {{ copied === row.index ? 'Copied' : 'Copy' }}
        </Button>
      </div>
      <p
        class="whitespace-pre-wrap cursor-pointer"
        :class="expanded ? '' : 'line-clamp-4'"
        title="Click to expand"
        @click="expanded = !expanded"
      >{{ row.revised_prompt }}</p>
    </div>
    <div v-if="seeds.length" class="flex flex-wrap gap-1">
      <Badge v-for="(s, i) in seeds" :key="i" variant="outline">seed {{ s }}</Badge>
    </div>
  </div>
</template>
