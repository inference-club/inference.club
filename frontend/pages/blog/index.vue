<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { data: posts } = await useAsyncData('blog:list', () =>
  queryCollection('blog')
    .order('publishedAt', 'DESC')
    .all(),
)

useSeoMeta({
  title: 'Blog · inference.club',
  description: 'Updates from the inference.club team and community.',
})

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
</script>

<template>
  <div class="container mx-auto p-6 max-w-3xl">
    <h1 class="text-3xl font-bold mb-8">Blog</h1>

    <div v-if="!posts || posts.length === 0" class="text-muted-foreground">
      No posts yet.
    </div>

    <ul class="space-y-8">
      <li v-for="post in posts" :key="post.path" class="border-b pb-8 last:border-b-0">
        <NuxtLink :to="post.path" class="block group">
          <h2 class="text-xl font-semibold group-hover:underline">
            {{ post.title }}
          </h2>
          <p class="text-sm text-muted-foreground mt-1">
            {{ formatDate(post.publishedAt) }}<template v-if="post.author"> · {{ post.author }}</template>
          </p>
          <p v-if="post.description" class="mt-3 text-muted-foreground">
            {{ post.description }}
          </p>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
