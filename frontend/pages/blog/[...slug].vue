<script setup lang="ts">
definePageMeta({ layout: 'default' })

const route = useRoute()
const localePath = useLocalePath()
const { findByPath, locale } = useLocalizedContent()

// Query the active locale's collection, falling back to English when the post
// isn't translated yet. `fellBack` drives the notice banner.
const { data } = await useAsyncData(
  `blog:${route.path}`,
  () => findByPath('blog', route.path),
)
const post = computed(() => data.value?.doc ?? null)
const fellBack = computed(() => data.value?.fellBack ?? false)

if (!post.value) {
  throw createError({ statusCode: 404, statusMessage: 'Post not found' })
}

// Build the canonical post URL. siteUrl could come from runtime config later;
// for now derive from the request host so dev and prod both work.
const requestUrl = useRequestURL()
const siteUrl = `${requestUrl.protocol}//${requestUrl.host}`
const postUrl = `${siteUrl}${route.path}`
const ogImageUrl = `${siteUrl}/images/inference-club.png`

// Reading time estimate at 200 wpm — handy SEO + UX touch.
const readingMinutes = computed(() => {
  const text = (post.value as unknown as { body?: { value?: unknown } }).body
  // ContentRenderer body is an AST; flatten conservatively to a string for counting.
  const flat = JSON.stringify(text ?? '')
  const words = flat.split(/\s+/).filter(Boolean).length
  return Math.max(1, Math.round(words / 1000)) // AST nodes inflate counts; divide harder than 200 wpm
})

useSeoMeta({
  title: `${post.value.title} · inference.club blog`,
  description: post.value.description,
  ogTitle: post.value.title,
  ogDescription: post.value.description,
  ogType: 'article',
  ogUrl: postUrl,
  ogImage: ogImageUrl,
  ogSiteName: 'inference.club',
  twitterCard: 'summary_large_image',
  twitterTitle: post.value.title,
  twitterDescription: post.value.description,
  twitterImage: ogImageUrl,
  articlePublishedTime: post.value.publishedAt,
  articleAuthor: post.value.author ? [post.value.author] : undefined,
  articleTag: post.value.tags,
})

// JSON-LD article schema for richer Google results.
useHead({
  link: [{ rel: 'canonical', href: postUrl }],
  script: [
    {
      type: 'application/ld+json',
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: post.value.title,
        description: post.value.description,
        image: ogImageUrl,
        datePublished: post.value.publishedAt,
        dateModified: post.value.publishedAt,
        author: post.value.author
          ? { '@type': 'Person', name: post.value.author }
          : { '@type': 'Organization', name: 'inference.club' },
        publisher: {
          '@type': 'Organization',
          name: 'inference.club',
          logo: { '@type': 'ImageObject', url: ogImageUrl },
        },
        mainEntityOfPage: { '@type': 'WebPage', '@id': postUrl },
      }),
    },
  ],
})

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
</script>

<template>
  <article
    class="container mx-auto px-4 sm:px-6 py-8 sm:py-12 max-w-3xl
           prose prose-neutral dark:prose-invert
           prose-headings:scroll-mt-20
           prose-pre:overflow-x-auto prose-pre:max-w-full
           prose-img:rounded-lg
           prose-a:underline-offset-4"
  >
    <ContentFallbackBanner v-if="fellBack" />
    <div
      v-if="post!.image"
      class="not-prose mb-8 sm:mb-10 rounded-xl overflow-hidden border shadow-sm"
    >
      <img
        :src="post!.image"
        :alt="post!.title"
        class="w-full aspect-[1536/640] object-cover"
      >
    </div>
    <header class="not-prose mb-8 sm:mb-10">
      <h1 class="text-3xl sm:text-4xl font-bold tracking-tight">
        {{ post!.title }}
      </h1>
      <p class="text-sm text-muted-foreground mt-3">
        <time :datetime="post!.publishedAt">{{ formatDate(post!.publishedAt) }}</time>
        <template v-if="post!.author">
          ·
          <NuxtLink
            :to="localePath(`/${post!.author}`)"
            class="hover:text-foreground underline-offset-4 hover:underline"
          >@{{ post!.author }}</NuxtLink>
        </template>
        <span class="mx-2">·</span>
        <span>{{ readingMinutes }} min read</span>
      </p>
      <div v-if="post!.tags?.length" class="mt-4 flex flex-wrap gap-2">
        <span
          v-for="tag in post!.tags"
          :key="tag"
          class="px-2 py-0.5 text-xs rounded bg-muted text-muted-foreground"
        >
          #{{ tag }}
        </span>
      </div>
    </header>
    <ContentRenderer :value="post!" />
    <footer class="not-prose mt-12 sm:mt-16 pt-8 border-t">
      <NuxtLink :to="localePath('/blog')" class="text-sm text-muted-foreground hover:text-foreground">
        ← {{ $t('common.allPosts') }}
      </NuxtLink>
    </footer>
  </article>
</template>
