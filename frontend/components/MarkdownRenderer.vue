<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

// Renders a markdown string as sanitized HTML. Parsing + sanitizing happen
// client-side (like CodeTabs does with shiki) so there's no SSR import cost
// and DOMPurify has a real DOM to work against. Before hydration (and as a
// no-JS / failure fallback) we show the escaped raw text, so content is never
// lost or unsafely injected.
const props = defineProps<{ content?: string | null }>()

const html = ref('')
const ready = ref(false)

const render = async () => {
  const content = props.content ?? ''
  ready.value = false
  if (!content.trim()) {
    html.value = ''
    ready.value = true
    return
  }
  try {
    const [{ marked }, dompurify] = await Promise.all([
      import('marked'),
      import('dompurify'),
    ])
    const DOMPurify = dompurify.default
    const parsed = await marked.parse(content, { breaks: true, gfm: true })
    html.value = DOMPurify.sanitize(parsed)
    ready.value = true
  } catch (err) {
    console.error('markdown render failed:', err)
    // Leave ready=false so the escaped <pre> fallback in the template shows.
  }
}

onMounted(render)
watch(() => props.content, render)
</script>

<template>
  <div class="prose prose-sm dark:prose-invert max-w-none break-words prose-pre:bg-zinc-950 prose-pre:text-zinc-100">
    <div v-if="ready" v-html="html" />
    <pre
      v-else
      class="whitespace-pre-wrap break-words font-sans text-sm m-0 bg-transparent p-0"
    >{{ content }}</pre>
  </div>
</template>
