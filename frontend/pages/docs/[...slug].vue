<script setup lang="ts">
definePageMeta({ layout: 'docs' })

const route = useRoute()

// queryCollection().path() takes the URL path. Our docs live at /docs/...
const { data: page } = await useAsyncData(
  `docs:${route.path}`,
  () => queryCollection('docs').path(route.path).first(),
)

if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Doc not found' })
}

useSeoMeta({
  title: page.value.title ? `${page.value.title} · inference.club docs` : 'inference.club docs',
  description: page.value.description,
})
</script>

<template>
  <article>
    <ContentRenderer v-if="page" :value="page" />
  </article>
</template>
