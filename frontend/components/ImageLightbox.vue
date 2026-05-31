<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { ExternalLink, X } from 'lucide-vue-next'

const { current, close } = useImageLightbox()

const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') close()
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
        <!-- Capped to the viewport; object-contain keeps the full image visible
             at its aspect ratio, never flowing off-screen. -->
        <img
          :src="current"
          alt="Generated image"
          class="max-h-[92vh] max-w-[92vw] rounded-lg object-contain shadow-2xl"
          @click.stop
        />
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
