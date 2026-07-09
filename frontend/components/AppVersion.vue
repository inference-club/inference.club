<script setup lang="ts">
// Small version/environment chip fed by GET /api/meta/. Fetches client-side on
// mount (non-blocking) and stays hidden until the metadata arrives.
const { meta, load } = useAppMeta()
onMounted(load)

const label = computed(() => {
  const v = meta.value?.version
  if (!v) return ''
  return v === 'dev' ? 'dev' : `v${v}`
})

// Badge only genuinely notable environments (home lab, staging, …). The
// "normal" cases — the public cloud and plain local dev — get no badge, so
// prod stays clean even before DEPLOY_ENV is explicitly set (defaults "local").
const showEnv = computed(() => {
  const env = meta.value?.env
  return !!env && !['cloud', 'local', ''].includes(env)
})

const title = computed(() => {
  if (!meta.value) return ''
  const { name, version, git_sha, env } = meta.value
  return [name, version, git_sha, env].filter(Boolean).join(' · ')
})
</script>

<template>
  <span
    v-if="meta"
    :title="title"
    class="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground/70"
  >
    <span>{{ label }}</span>
    <span
      v-if="showEnv"
      class="rounded bg-muted px-1 py-0.5 uppercase tracking-wide"
    >{{ meta.env }}</span>
  </span>
</template>
