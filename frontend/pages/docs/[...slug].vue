<script setup lang="ts">
definePageMeta({ layout: 'docs' })

const route = useRoute()
const { findByPath } = useLocalizedContent()

// Active-locale docs page, falling back to English when untranslated.
const { data } = await useAsyncData(
  `docs:${route.path}`,
  () => findByPath('docs', route.path),
)
const page = computed(() => data.value?.doc ?? null)
const fellBack = computed(() => data.value?.fellBack ?? false)

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
    <ContentFallbackBanner v-if="fellBack" />
    <ContentRenderer v-if="page" :value="page" />
  </article>
</template>
