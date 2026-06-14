<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-vue-next'

const { current, list, index, prev, next, close, hasNav } = useImageLightbox()

const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="lb-fade">
      <div
        v-if="current"
        class="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
        @click="close"
      >
        <!-- Main image -->
        <img
          :src="current"
          alt="Generated image"
          class="max-h-[92vh] max-w-[92vw] rounded-lg object-contain shadow-2xl"
          @click.stop
        />

        <!-- Prev / Next arrows -->
        <template v-if="hasNav">
          <button
            class="absolute left-3 top-1/2 -translate-y-1/2 flex size-11 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/30 transition-colors"
            title="Previous (←)"
            @click.stop="prev"
          >
            <ChevronLeft class="size-6" />
          </button>
          <button
            class="absolute right-3 top-1/2 -translate-y-1/2 flex size-11 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/30 transition-colors"
            title="Next (→)"
            @click.stop="next"
          >
            <ChevronRight class="size-6" />
          </button>
        </template>

        <!-- Top-right controls -->
        <div class="absolute right-4 top-4 flex items-center gap-2" @click.stop>
          <a
            :href="current"
            target="_blank"
            rel="noopener"
            class="flex size-9 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25"
            title="Open in new tab"
          >
            <ExternalLink class="size-4" />
          </a>
          <button
            class="flex size-9 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25"
            title="Close (Esc)"
            @click="close"
          >
            <X class="size-5" />
          </button>
        </div>

        <!-- Position counter -->
        <div
          v-if="hasNav"
          class="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-xs text-white/80 tabular-nums"
          @click.stop
        >
          {{ index + 1 }} / {{ list.length }}
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.lb-fade-enter-active,
.lb-fade-leave-active {
  transition: opacity 0.15s ease;
}
.lb-fade-enter-from,
.lb-fade-leave-to {
  opacity: 0;
}
</style>
