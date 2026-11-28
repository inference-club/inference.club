<script setup lang="ts">
// The page a share link opens. Built to be passed around: the result first,
// who made it and on what hardware, the prompt, and a way to make your own.
import { computed, onMounted } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useContentSharing } from '@/composables/useContentSharing'
import { requestPrompt, requestTitle } from '@/utils/requestView'

const { t } = useI18n()
const route = useRoute()
const token = computed(() => String(route.params.token || ''))
const { getSharedRequest } = useContentSharing()

// SSR-fetch so social crawlers get the OG tags below.
const { data: req, pending: loading, error, refresh } = await useAsyncData(
  () => `shared-${token.value}`,
  () => getSharedRequest(token.value),
)
// The server render has no session, so something only its owner (or a member)
// may see fails there. Ask again from the browser, which has the cookie.
onMounted(() => {
  if (error.value) refresh()
})
const notFound = computed(() => !!error.value)

const owner = computed(() => req.value?.github_login || req.value?.owner || '')
const title = computed(() =>
  req.value ? requestTitle(req.value, t(`request.kind.${req.value.inference_type}`)) : '',
)
const about = computed(() => {
  if (!req.value) return t('request.sharePage.fallback')
  const by = owner.value ? `@${owner.value}` : 'inference.club'
  const made = t('request.sharePage.madeWith', { model: req.value.model_name || 'open models', by })
  const words = requestPrompt(req.value)
  return words && words !== title.value ? `${words.slice(0, 160)} · ${made}` : made
})
const audio = computed(() =>
  req.value && ['MUSIC', 'TTS'].includes(req.value.inference_type)
    ? req.value.output_audio_url
    : undefined,
)

// Social preview so shared links unfurl well in chat apps. WebGL can't be
// scraped, so a 3D model unfurls with its source image; a video with its first
// frame; a song with its cover.
useSeoMeta({
  title: () => (title.value ? `${title.value} · inference.club` : 'inference.club'),
  description: () => about.value,
  ogTitle: () => title.value || 'inference.club',
  ogDescription: () => about.value,
  ogSiteName: 'inference.club',
  ogType: () => (req.value?.video_url ? 'video.other' : audio.value ? 'music.song' : 'article'),
  ogImage: () =>
    req.value?.image_urls?.[0] || req.value?.cover_image_url || req.value?.input_image_url || undefined,
  ogVideo: () => req.value?.video_url || undefined,
  ogAudio: () => audio.value || undefined,
  twitterCard: () =>
    req.value?.image_urls?.[0] || req.value?.cover_image_url || req.value?.input_image_url
      ? 'summary_large_image'
      : 'summary',
})
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-3 py-6 sm:px-6 sm:py-10">
    <div v-if="loading" class="space-y-4">
      <div class="h-8 w-64 animate-pulse rounded bg-muted" />
      <div class="h-72 animate-pulse rounded-2xl bg-muted" />
    </div>

    <div v-else-if="notFound" class="py-20 text-center">
      <h1 class="mb-2 text-xl font-semibold">{{ t('request.sharePage.goneTitle') }}</h1>
      <p class="text-muted-foreground">{{ t('request.sharePage.goneBody') }}</p>
      <Button as-child variant="outline" class="mt-6">
        <NuxtLink to="/">{{ t('request.sharePage.home') }}</NuxtLink>
      </Button>
    </div>

    <template v-else-if="req">
      <RequestView :request="req">
        <template #actions>
          <RequestActionBar :request="req" :show-share="false" />
          <ShareButton :text="title" variant="default" />
        </template>
      </RequestView>

      <!-- Make your own -->
      <aside
        class="mt-8 flex flex-col items-start gap-3 rounded-2xl border bg-gradient-to-br from-primary/10 via-transparent to-transparent p-5 sm:flex-row sm:items-center sm:justify-between"
        data-testid="share-cta"
      >
        <div class="min-w-0">
          <p class="font-semibold">{{ t('request.sharePage.ctaTitle') }}</p>
          <p class="text-sm text-muted-foreground">{{ t('request.sharePage.ctaBody') }}</p>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button v-if="owner" as-child variant="outline">
            <NuxtLink :to="`/${owner}`">{{ t('request.sharePage.more', { owner: `@${owner}` }) }}</NuxtLink>
          </Button>
          <Button as-child class="gap-2">
            <NuxtLink to="/">{{ t('request.sharePage.cta') }} <ArrowRight class="size-4" /></NuxtLink>
          </Button>
        </div>
      </aside>
    </template>
  </div>
</template>
