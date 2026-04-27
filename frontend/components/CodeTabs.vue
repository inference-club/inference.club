<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Check, Copy } from 'lucide-vue-next'

interface Snippet {
  label: string
  lang: string
  code: string
}

const props = defineProps<{
  snippets: Snippet[]
  filename?: string
}>()

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

const active = ref(0)
const copied = ref(false)
const rendered = ref<string[]>(
  props.snippets.map(s => `<pre><code>${escapeHtml(s.code)}</code></pre>`),
)

onMounted(async () => {
  try {
    const { codeToHtml } = await import('shiki')
    rendered.value = await Promise.all(
      props.snippets.map(s =>
        codeToHtml(s.code, { lang: s.lang, theme: 'github-dark-default' }),
      ),
    )
  } catch (err) {
    console.error('shiki render failed:', err)
  }
})

const copy = async () => {
  await navigator.clipboard.writeText(props.snippets[active.value].code)
  copied.value = true
  setTimeout(() => { copied.value = false }, 1600)
}

watch(active, () => { copied.value = false })
</script>

<template>
  <div class="rounded-xl border border-white/10 bg-zinc-950 shadow-2xl shadow-black/40 overflow-hidden">
    <div class="flex items-center justify-between border-b border-white/10 bg-zinc-900/40 pl-2 pr-3">
      <div class="flex items-center">
        <button
          v-for="(s, i) in snippets"
          :key="s.label"
          type="button"
          class="px-3 py-2 text-xs font-mono transition-colors relative"
          :class="active === i
            ? 'text-zinc-100'
            : 'text-zinc-500 hover:text-zinc-300'"
          @click="active = i"
        >
          {{ s.label }}
          <span
            v-if="active === i"
            class="absolute bottom-0 left-1 right-1 h-px bg-gradient-to-r from-violet-400 via-fuchsia-400 to-cyan-400"
          />
        </button>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="filename" class="text-[10px] uppercase tracking-wider text-zinc-600 font-mono hidden sm:block">
          {{ filename }}
        </span>
        <button
          type="button"
          class="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-white/5 transition-colors"
          :aria-label="copied ? 'Copied' : 'Copy'"
          @click="copy"
        >
          <Check v-if="copied" class="h-3.5 w-3.5 text-emerald-400" />
          <Copy v-else class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
    <div class="relative">
      <div
        v-for="(s, i) in snippets"
        :key="s.label"
        v-show="active === i"
        class="code-scroll overflow-x-auto text-sm text-zinc-100"
        v-html="rendered[i] ?? ''"
      />
    </div>
  </div>
</template>

<style scoped>
.code-scroll :deep(pre),
.code-scroll :deep(code) {
  margin: 0;
  padding: 0;
  background: transparent !important;
  line-height: 1.5;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
.code-scroll :deep(pre) {
  padding: 1.25rem;
}
.code-scroll :deep(.line) {
  display: inline-block;
  min-height: 1em;
  line-height: 1.5;
}
.code-scroll {
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.code-scroll::-webkit-scrollbar {
  display: none;
}
</style>
