<script setup lang="ts">
definePageMeta({ layout: 'docs' })

// The /docs root is rendered from content/<locale>/docs/index.md so editors
// don't need to touch Vue to change the landing page. Falls back to English.
const { findByPath } = useLocalizedContent()
const { data } = await useAsyncData('docs:/docs', () => findByPath('docs', '/docs'))
const page = computed(() => data.value?.doc ?? null)

useSeoMeta({
  title: 'inference.club docs',
  description: page.value?.description ?? 'inference.club documentation',
})
</script>

<template>
  <article class="prose prose-neutral dark:prose-invert mx-auto min-w-0 max-w-3xl break-words">
    <ContentRenderer v-if="page" :value="page" />
    <p v-else>Docs landing page is missing — check that <code>content/docs/index.md</code> exists.</p>
  </article>
</template>
