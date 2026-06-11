<script setup lang="ts">
definePageMeta({ layout: 'app', middleware: 'staff' })

const buttonVariants = ['default', 'secondary', 'outline', 'ghost', 'destructive', 'link'] as const
const badgeVariants = ['default', 'secondary', 'outline', 'destructive'] as const
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-4 sm:px-6 py-6">
    <h1 class="text-2xl font-semibold tracking-tight">Primitives</h1>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Buttons</h2>
      <div class="flex flex-wrap items-center gap-2">
        <Button v-for="v in buttonVariants" :key="v" :variant="v">{{ v }}</Button>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm">small</Button>
        <Button>default</Button>
        <Button size="lg">large</Button>
        <Button disabled>disabled</Button>
      </div>
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Badges</h2>
      <div class="flex flex-wrap items-center gap-2">
        <Badge v-for="v in badgeVariants" :key="v" :variant="v">{{ v }}</Badge>
        <VisibilityBadge visibility="PUBLIC" />
        <VisibilityBadge visibility="UNLISTED" />
        <VisibilityBadge visibility="PRIVATE" />
        <VisibilityBadge visibility="SECRET" />
      </div>
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Inputs</h2>
      <div class="grid max-w-sm gap-3">
        <Input placeholder="Text input" />
        <Input placeholder="Disabled" disabled />
        <Textarea placeholder="Textarea" />
      </div>
    </section>

    <section class="mt-8">
      <h2 class="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Cards</h2>
      <Card class="p-4">
        <p class="font-medium">Card title</p>
        <p class="mt-0.5 text-sm text-muted-foreground">
          Supporting copy at the muted level. Cards are the unit of almost every page.
        </p>
      </Card>
    </section>
  </div>
</template>
