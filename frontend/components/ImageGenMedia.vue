<script setup lang="ts">
import { computed } from 'vue'

// Unified renderer for an image-generation request's pictures, used on the
// card, the request detail page and the public share page. It picks the
// layout from the data:
//   • exactly one source + one result  → draggable before/after slider
//   • anything else (multi-reference edit, plain text-to-image, N results)
//     → a labelled grid of sources then results
// Every picture opens the shared lightbox over the combined [sources, results]
// list, so the arrows cycle through inputs and outputs alike (looping).
const props = withDefaults(
  defineProps<{
    inputs?: string[] | null
    outputs?: string[] | null
    // Compact tunes sizing for the dense card; full is for detail/share pages.
    compact?: boolean
  }>(),
  { inputs: () => [], outputs: () => [], compact: false },
)

const inputs = computed(() => props.inputs ?? [])
const outputs = computed(() => props.outputs ?? [])
const all = computed(() => [...inputs.value, ...outputs.value])
const isCompare = computed(() => inputs.value.length === 1 && outputs.value.length === 1)

const lightbox = useImageLightbox()
const openAt = (i: number) => lightbox.openList(all.value, i)

// Output grid only doubles up when compact and there's more than one.
const gridCols = computed(() =>
  props.compact && outputs.value.length > 1 ? 'grid-cols-2' : 'grid-cols-1',
)
</script>

<template>
  <div class="flex flex-col gap-2">
    <!-- Single edit: before/after compare slider -->
    <ImageCompareSlider
      v-if="isCompare"
      :before="inputs[0]"
      :after="outputs[0]"
      @expand="openAt(inputs.length)"
    />

    <template v-else>
      <!-- Source / reference images -->
      <div v-if="inputs.length" class="min-w-0">
        <p class="mb-1 text-2xs uppercase tracking-wider text-muted-foreground">
          {{ inputs.length > 1 ? `${inputs.length} references` : 'Source' }}
        </p>
        <div class="flex flex-wrap gap-1.5">
          <img
            v-for="(url, i) in inputs"
            :key="`in-${i}`"
            :src="url"
            class="cursor-zoom-in rounded-lg border object-cover opacity-90 transition-opacity hover:opacity-100"
            :class="compact ? 'size-16' : 'max-h-40 w-auto'"
            loading="lazy"
            alt="Source image"
            @click.stop="openAt(i)"
          >
        </div>
      </div>

      <!-- Generated results -->
      <div v-if="outputs.length" class="min-w-0">
        <p
          v-if="inputs.length"
          class="mb-1 text-2xs uppercase tracking-wider text-muted-foreground"
        >
          {{ outputs.length > 1 ? 'Results' : 'Result' }}
        </p>
        <div class="grid gap-1.5" :class="gridCols">
          <img
            v-for="(url, i) in (compact ? outputs.slice(0, 4) : outputs)"
            :key="`out-${i}`"
            :src="url"
            class="cursor-zoom-in rounded-lg border transition-opacity hover:opacity-90"
            :class="compact ? 'h-full max-h-80 min-h-32 w-full object-cover' : 'max-h-[75vh] w-auto object-contain'"
            loading="lazy"
            alt="Generated image"
            @click.stop="openAt(inputs.length + i)"
          >
        </div>
      </div>

      <p v-if="!all.length" class="text-sm text-muted-foreground">—</p>
    </template>
  </div>
</template>
