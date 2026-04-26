<script setup lang="ts">
definePageMeta({ layout: 'default' })

const route = useRoute()

const { data: post } = await useAsyncData(
  `blog:${route.path}`,
  () => queryCollection('blog').path(route.path).first(),
)

if (!post.value) {
  throw createError({ statusCode: 404, statusMessage: 'Post not found' })
}

useSeoMeta({
  title: `${post.value.title} · inference.club blog`,
  description: post.value.description,
})

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
</script>

<template>
  <article class="container mx-auto px-6 py-10 max-w-3xl prose prose-neutral dark:prose-invert">
    <header class="not-prose mb-8">
      <h1 class="text-3xl font-bold">{{ post!.title }}</h1>
      <p class="text-sm text-muted-foreground mt-2">
        {{ formatDate(post!.publishedAt) }}<template v-if="post!.author"> · {{ post!.author }}</template>
      </p>
    </header>
    <ContentRenderer :value="post!" />
  </article>
</template>
