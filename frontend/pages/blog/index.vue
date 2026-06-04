<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { t, locale } = useI18n()
const localePath = useLocalePath()
const { listMerged } = useLocalizedContent()

// Translated posts for the active locale, merged with English posts that aren't
// translated yet (flagged isFallback → "EN" badge). Re-runs on locale change.
const { data: posts } = await useAsyncData(
  'blog:list',
  () => listMerged('blog', q => q.order('publishedAt', 'DESC')),
  { watch: [locale] },
)

useSeoMeta({
  title: () => `${t('blog.title')} · inference.club`,
  description: () => t('blog.subtitle'),
})

const hero = computed(() => posts.value?.[0])
const rest = computed(() => posts.value?.slice(1) ?? [])

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(locale.value, { year: 'numeric', month: 'long', day: 'numeric' })
</script>

<template>
  <div class="container mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 max-w-5xl">
    <header class="mb-10">
      <h1 class="text-4xl font-bold tracking-tight">{{ t('blog.title') }}</h1>
      <p class="text-muted-foreground mt-2">
        {{ t('blog.subtitle') }}
      </p>
    </header>

    <div v-if="!posts || posts.length === 0" class="text-muted-foreground">
      {{ t('blog.noPosts') }}
    </div>

    <template v-else>
      <!-- Featured / newest -->
      <NuxtLink
        :to="localePath(hero!.path)"
        class="group block rounded-2xl border bg-card overflow-hidden shadow-sm hover:shadow-md hover:border-primary/40 transition-all mb-10"
      >
        <div class="grid md:grid-cols-2">
          <div class="relative aspect-[16/10] md:aspect-auto md:min-h-[20rem] overflow-hidden">
            <img
              v-if="hero!.image"
              :src="hero!.image"
              :alt="hero!.title"
              class="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            >
            <div
              v-else
              class="absolute inset-0 bg-gradient-to-br from-violet-500/30 via-fuchsia-500/20 to-cyan-500/30"
            />
          </div>
          <div class="p-6 sm:p-8 flex flex-col justify-center">
            <p class="text-xs uppercase tracking-wide text-primary font-medium mb-2">
              {{ t('blog.latest') }}
              <span v-if="hero!.isFallback" class="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{{ t('content.englishBadge') }}</span>
            </p>
            <h2 class="text-2xl font-bold tracking-tight group-hover:text-primary transition-colors">
              {{ hero!.title }}
            </h2>
            <p class="text-sm text-muted-foreground mt-2">
              {{ formatDate(hero!.publishedAt) }}<template v-if="hero!.author"> · @{{ hero!.author }}</template>
            </p>
            <p v-if="hero!.description" class="mt-4 text-muted-foreground line-clamp-3">
              {{ hero!.description }}
            </p>
            <div v-if="hero!.tags?.length" class="mt-5 flex flex-wrap gap-1.5">
              <span
                v-for="tag in hero!.tags"
                :key="tag"
                class="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground"
              >
                #{{ tag }}
              </span>
            </div>
          </div>
        </div>
      </NuxtLink>

      <!-- Rest -->
      <div v-if="rest.length" class="grid gap-6 sm:grid-cols-2">
        <article
          v-for="post in rest"
          :key="post.path"
          class="group rounded-xl border bg-card overflow-hidden shadow-sm hover:shadow-md hover:border-primary/40 transition-all"
        >
          <NuxtLink :to="localePath(post.path)" class="block">
            <div class="relative aspect-[16/9] overflow-hidden">
              <img
                v-if="post.image"
                :src="post.image"
                :alt="post.title"
                class="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
              >
              <div
                v-else
                class="absolute inset-0 bg-gradient-to-br from-violet-500/25 via-fuchsia-500/15 to-cyan-500/25"
              />
            </div>
            <div class="p-5">
              <p class="text-xs text-muted-foreground">
                {{ formatDate(post.publishedAt) }}<template v-if="post.author"> · @{{ post.author }}</template>
              </p>
              <h3 class="mt-1.5 text-lg font-semibold tracking-tight group-hover:text-primary transition-colors">
                {{ post.title }}
                <span v-if="post.isFallback" class="ml-1 align-middle rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">{{ t('content.englishBadge') }}</span>
              </h3>
              <p v-if="post.description" class="mt-2 text-sm text-muted-foreground line-clamp-2">
                {{ post.description }}
              </p>
              <div v-if="post.tags?.length" class="mt-4 flex flex-wrap gap-1.5">
                <span
                  v-for="tag in post.tags"
                  :key="tag"
                  class="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground"
                >
                  #{{ tag }}
                </span>
              </div>
            </div>
          </NuxtLink>
        </article>
      </div>
    </template>
  </div>
</template>
