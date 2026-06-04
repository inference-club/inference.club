<script setup lang="ts">
import { computed } from 'vue'
import { Globe, Link2, Users, Lock } from 'lucide-vue-next'
import type { Visibility } from '@/types'
import { VISIBILITY_META } from '@/utils/visibility'

const props = withDefaults(
  defineProps<{ visibility?: Visibility; iconOnly?: boolean }>(),
  { iconOnly: false },
)

const ICONS: Record<Visibility, typeof Globe> = {
  PUBLIC: Globe,
  UNLISTED: Link2,
  PRIVATE: Users,
  SECRET: Lock,
}

const meta = computed(() =>
  props.visibility ? VISIBILITY_META[props.visibility] : null,
)
const icon = computed(() => (props.visibility ? ICONS[props.visibility] : Globe))
</script>

<template>
  <Badge
    v-if="meta"
    variant="outline"
    class="gap-1"
    :title="meta.description"
  >
    <component :is="icon" class="size-3" />
    <span v-if="!iconOnly">{{ meta.short }}</span>
  </Badge>
</template>
