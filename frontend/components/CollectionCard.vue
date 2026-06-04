<script setup lang="ts">
import { Folder, Layers } from 'lucide-vue-next'
import type { Collection } from '@/types'

defineProps<{ collection: Collection; to: string }>()
</script>

<template>
  <NuxtLink
    :to="to"
    class="block rounded-lg border overflow-hidden hover:border-primary/50 hover:bg-accent/30 transition-colors group"
  >
    <div class="aspect-[16/9] bg-muted/40 overflow-hidden flex items-center justify-center">
      <img
        v-if="collection.cover_image_url"
        :src="collection.cover_image_url"
        class="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
        loading="lazy"
      />
      <Folder v-else class="size-10 text-muted-foreground/40" />
    </div>
    <div class="p-3">
      <div class="flex items-center justify-between gap-2">
        <h3 class="font-medium truncate">{{ collection.name }}</h3>
        <VisibilityBadge :visibility="collection.visibility" icon-only />
      </div>
      <p v-if="collection.description" class="text-xs text-muted-foreground mt-1 line-clamp-2">
        {{ collection.description }}
      </p>
      <p class="text-xs text-muted-foreground mt-2 inline-flex items-center gap-1">
        <Layers class="size-3" />
        {{ collection.item_count }} item{{ collection.item_count === 1 ? '' : 's' }}
      </p>
    </div>
  </NuxtLink>
</template>
