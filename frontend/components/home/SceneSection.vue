<script setup lang="ts">
// One homepage section built around a visual: a short heading and paragraph,
// then whatever is in the default slot (usually a SceneStage), then an
// optional row of notes beneath it.
defineProps<{ eyebrow: string; title: string; body: string; id?: string }>()
</script>

<template>
  <section :id="id" class="scroll-mt-16 px-4 py-14 sm:px-6 sm:py-20 lg:px-8">
    <div class="mx-auto max-w-6xl">
      <div class="mb-7 max-w-2xl sm:mb-9">
        <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ eyebrow }}</p>
        <h2 class="text-3xl font-bold tracking-tight sm:text-5xl">{{ title }}</h2>
        <p class="mt-4 leading-relaxed text-muted-foreground">{{ body }}</p>
      </div>
      <slot />
      <div v-if="$slots.notes" class="mt-4"><slot name="notes" /></div>
    </div>
  </section>
</template>
