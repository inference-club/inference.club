<script setup lang="ts">
import { onMounted, ref } from 'vue'

definePageMeta({ layout: 'default' })

const config = useRuntimeConfig()
// The spec is served by the API itself, so it always describes the live
// surface and is importable from api.inference.club/openapi.json too.
const specUrl = `${config.public.apiBase}/openapi.json`

useSeoMeta({
  title: 'API reference · inference.club',
  description:
    'Interactive reference for the OpenAI-compatible inference.club API — chat, transcription, and image endpoints.',
})

const SWAGGER_VERSION = '5'
const cssHref = `https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_VERSION}/swagger-ui.css`
const jsSrc = `https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_VERSION}/swagger-ui-bundle.js`

useHead({
  link: [{ rel: 'stylesheet', href: cssHref }],
})

const failed = ref(false)

const initSwagger = () => {
  const SwaggerUIBundle = (window as unknown as { SwaggerUIBundle?: any }).SwaggerUIBundle
  if (!SwaggerUIBundle) {
    failed.value = true
    return
  }
  SwaggerUIBundle({
    url: specUrl,
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout',
    tryItOutEnabled: true,
    persistAuthorization: true,
    defaultModelsExpandDepth: 0,
  })
}

onMounted(() => {
  // Already loaded (client navigation back to this page).
  if ((window as unknown as { SwaggerUIBundle?: unknown }).SwaggerUIBundle) {
    initSwagger()
    return
  }
  const s = document.createElement('script')
  s.src = jsSrc
  s.crossOrigin = 'anonymous'
  s.onload = initSwagger
  s.onerror = () => (failed.value = true)
  document.body.appendChild(s)
})
</script>

<template>
  <div class="container mx-auto max-w-6xl px-4 py-8">
    <header class="mb-6">
      <h1 class="text-3xl font-bold">API reference</h1>
      <p class="mt-2 max-w-2xl text-muted-foreground">
        The inference.club API is OpenAI-compatible — point any OpenAI client at
        <code class="rounded bg-muted px-1.5 py-0.5 text-sm">https://api.inference.club/v1</code>.
        Get a key from <NuxtLink to="/dashboard/settings/token" class="text-primary underline">Settings → Token</NuxtLink>,
        click <strong>Authorize</strong> below to try requests live, or import the spec from
        <a :href="specUrl" target="_blank" rel="noopener" class="text-primary underline">openapi.json</a>.
      </p>
      <p class="mt-2 text-xs text-muted-foreground">
        Note: “Try it out” sends real requests to a live provider's GPU using your API key and counts against your rate limit.
      </p>
    </header>

    <div v-if="failed" class="rounded-lg border bg-muted/40 p-4 text-sm">
      Couldn't load the API explorer. You can still view or import the spec directly at
      <a :href="specUrl" target="_blank" rel="noopener" class="text-primary underline">{{ specUrl }}</a>.
    </div>

    <!-- Swagger UI mounts here (light theme; kept on a white card so it reads
         well in dark mode too). -->
    <div class="overflow-hidden rounded-xl border bg-white">
      <div id="swagger-ui" />
    </div>
  </div>
</template>

<style>
/* Trim Swagger UI's default outer padding/shadow since we wrap it in a card. */
#swagger-ui .swagger-ui .topbar {
  display: none;
}
#swagger-ui .swagger-ui {
  padding: 0.5rem 0;
}
</style>
