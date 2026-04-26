<script setup lang="ts">
definePageMeta({ layout: 'docs' })

// The /docs root is rendered from content/docs/index.md so editors don't
// need to touch Vue to change the landing page.
const { data: page } = await useAsyncData('docs:/docs', () =>
  queryCollection('docs').path('/docs').first(),
)

useSeoMeta({
  title: 'inference.club docs',
  description: page.value?.description ?? 'inference.club documentation',
})
</script>

<template>
  <article>
    <ContentRenderer v-if="page" :value="page" />
    <p v-else>Docs landing page is missing — check that <code>content/docs/index.md</code> exists.</p>
  </article>
</template>
