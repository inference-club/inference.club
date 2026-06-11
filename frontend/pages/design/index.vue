<script setup lang="ts">
// Component design gallery — the in-app workbench for reviewing components
// in every state at both viewports (docs/prd/05-design-quality-and-visual-
// testing.md). Staff-gated; seeded designbot is staff, so the Playwright
// suite screenshots these pages on desktop + mobile automatically.
definePageMeta({ layout: 'app', middleware: 'staff' })

const sections = [
  {
    to: '/design/cards',
    title: 'Inference request cards',
    desc: 'All 7 modalities, owner/public variants, and the worst-case overflow fixtures.',
  },
  {
    to: '/design/primitives',
    title: 'Primitives',
    desc: 'Buttons, badges, inputs, alerts — the shadcn building blocks in both themes.',
  },
]
</script>

<template>
  <div class="mx-auto max-w-3xl p-6">
    <h1 class="text-2xl font-semibold tracking-tight">Design gallery</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Components in every state, rendered by the real app. The Playwright design suite
      screenshots these pages at desktop and mobile widths (<code class="text-xs">npm run shots</code>).
    </p>

    <div class="mt-6 grid gap-3">
      <NuxtLink v-for="s in sections" :key="s.to" :to="s.to">
        <Card class="p-4 transition-colors hover:border-primary/50 hover:bg-accent/30">
          <p class="font-medium">{{ s.title }}</p>
          <p class="mt-0.5 text-sm text-muted-foreground">{{ s.desc }}</p>
        </Card>
      </NuxtLink>
    </div>
  </div>
</template>
