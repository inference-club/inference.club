<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy } from 'lucide-vue-next'

defineProps<{
  code: string
  label?: string
  lang?: string
}>()

const copied = ref(false)
const copy = async (code: string) => {
  await navigator.clipboard.writeText(code)
  copied.value = true
  setTimeout(() => { copied.value = false }, 1600)
}
</script>

<template>
  <div class="rounded-lg border bg-zinc-950 text-zinc-100 overflow-hidden">
    <div
      v-if="label || lang"
      class="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900/60 text-xs"
    >
      <span class="text-zinc-400 font-mono">{{ label }}</span>
      <span v-if="lang" class="text-zinc-500 uppercase tracking-wide">{{ lang }}</span>
    </div>
    <div class="relative">
      <button
        type="button"
        class="absolute top-2 right-2 p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors"
        :aria-label="copied ? 'Copied' : 'Copy code'"
        @click="copy(code)"
      >
        <Check v-if="copied" class="h-3.5 w-3.5 text-green-400" />
        <Copy v-else class="h-3.5 w-3.5" />
      </button>
      <pre class="overflow-x-auto p-4 text-sm leading-relaxed font-mono"><code>{{ code }}</code></pre>
    </div>
  </div>
</template>
