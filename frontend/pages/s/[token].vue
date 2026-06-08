<script setup lang="ts">
import { computed } from 'vue'
import { Github, Cpu, Server, ExternalLink } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useContentSharing } from '@/composables/useContentSharing'
import { roleClasses } from '@/utils/inference'

const route = useRoute()
const token = computed(() => String(route.params.token || ''))
const { getSharedRequest } = useContentSharing()

// SSR-fetch so social crawlers get the OG tags below.
const { data: req, pending: loading, error } = await useAsyncData(
  () => `shared-${token.value}`,
  () => getSharedRequest(token.value),
)
const notFound = computed(() => !!error.value)

const isStt = computed(() => req.value?.inference_type === 'STT')
const isImage = computed(() => req.value?.inference_type === 'IMAGE')
const isTts = computed(() => req.value?.inference_type === 'TTS')
const isMesh = computed(() => req.value?.inference_type === 'MESH')
const lightbox = useImageLightbox()

// Social/OG preview so shared links unfurl nicely in chat apps.
useSeoMeta({
  title: () =>
    req.value
      ? `${req.value.inference_type} request by @${req.value.github_login || req.value.owner || 'someone'} · inference.club`
      : 'Shared inference request · inference.club',
  description: () =>
    req.value?.prompt_preview || 'A shared inference request on inference.club.',
  ogTitle: () =>
    req.value ? `${req.value.inference_type} on inference.club` : 'inference.club',
  ogDescription: () => req.value?.prompt_preview || 'Shared inference request',
  // WebGL can't be scraped, so a shared 3D model unfurls with its source image.
  ogImage: () => req.value?.image_urls?.[0] || req.value?.input_image_url || undefined,
  twitterCard: 'summary_large_image',
})
</script>

<template>
  <div class="container mx-auto py-8 max-w-3xl px-4">
    <div v-if="loading" class="space-y-4">
      <div class="h-8 w-64 bg-muted rounded animate-pulse" />
      <Card class="p-4 animate-pulse h-48" />
    </div>

    <div v-else-if="notFound" class="text-center py-20">
      <h1 class="text-xl font-semibold mb-2">Not available</h1>
      <p class="text-muted-foreground">
        This request is private or the link is invalid.
      </p>
      <Button as-child variant="outline" class="mt-6">
        <NuxtLink to="/">Go to inference.club</NuxtLink>
      </Button>
    </div>

    <template v-else-if="req">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 mb-4">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <Badge variant="outline">{{ req.inference_type }}</Badge>
            <VisibilityBadge v-if="req.visibility" :visibility="req.visibility" />
            <a
              v-if="req.github_login"
              :href="`https://github.com/${req.github_login}`"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-md border font-mono hover:bg-accent transition-colors"
            >
              <Github class="size-3" /> {{ req.github_login }}
            </a>
          </div>
          <div class="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
            <span v-if="req.model_name" class="inline-flex items-center gap-1 font-mono">
              <Cpu class="size-3" /> {{ req.model_name }}
            </span>
            <span v-if="req.provider" class="inline-flex items-center gap-1">
              <Server class="size-3" /> {{ req.provider.name }}
            </span>
          </div>
        </div>
        <RequestActionBar :request="req" :show-share="false" />
      </div>

      <!-- Images -->
      <Card v-if="isImage" class="p-4 mb-4">
        <p v-if="req.prompt_preview" class="text-sm mb-3">
          <span class="text-muted-foreground">Prompt:</span> {{ req.prompt_preview }}
        </p>
        <div class="flex flex-wrap gap-3">
          <img
            v-for="(url, i) in req.image_urls"
            :key="i"
            :src="url"
            class="max-h-[70vh] w-auto cursor-zoom-in rounded-lg border object-contain"
            @click="lightbox.open(url)"
          />
        </div>
      </Card>

      <!-- Image to 3D -->
      <Card v-else-if="isMesh" class="p-4 mb-4">
        <ModelViewer
          v-if="req.model_url"
          :src="req.model_url"
          :poster-src="req.input_image_url"
          alt="Generated 3D model"
        />
        <div v-if="req.mesh" class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span v-if="req.mesh.vertices != null">{{ req.mesh.vertices.toLocaleString() }} vertices</span>
          <span v-if="req.mesh.faces != null">{{ req.mesh.faces.toLocaleString() }} faces</span>
        </div>
      </Card>

      <!-- Audio (TTS / STT) -->
      <Card v-else-if="isTts || isStt" class="p-4 mb-4">
        <p v-if="req.prompt_preview" class="text-sm mb-3">{{ req.prompt_preview }}</p>
        <audio
          v-if="req.output_audio_url || req.audio_url"
          :src="req.output_audio_url || req.audio_url || ''"
          controls
          class="w-full h-10"
        />
        <p v-if="isStt && req.response_text" class="text-sm mt-3">{{ req.response_text }}</p>
      </Card>

      <!-- Conversation + response (LLM) -->
      <template v-else>
        <Card v-if="req.messages?.length" class="p-4 mb-4">
          <h2 class="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">
            Conversation
          </h2>
          <div class="space-y-3">
            <div v-for="(m, i) in req.messages" :key="i" class="rounded-lg border p-3">
              <span
                class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium capitalize mb-2"
                :class="roleClasses(m.role)"
              >
                {{ m.role || 'message' }}
              </span>
              <MarkdownRenderer :content="m.content" />
            </div>
          </div>
        </Card>

        <Card v-if="req.response_text" class="p-4 mb-4">
          <h2 class="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">
            Response
          </h2>
          <div class="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
            <MarkdownRenderer :content="req.response_text" />
          </div>
        </Card>
      </template>

      <p class="text-center text-xs text-muted-foreground mt-8">
        Shared via
        <NuxtLink to="/" class="underline inline-flex items-center gap-1">
          inference.club <ExternalLink class="size-3" />
        </NuxtLink>
      </p>
    </template>
  </div>
</template>
