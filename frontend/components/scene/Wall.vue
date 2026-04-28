<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

const props = withDefaults(defineProps<{
  position: [number, number, number]
  size: [number, number, number]
  color?: string
}>(), {
  color: undefined,
})

const { palette } = useScenePalette()
</script>

<template>
  <TresMesh :position="props.position">
    <TresBoxGeometry :args="size" />
    <TresMeshStandardMaterial :color="color ?? palette.wall" :roughness="0.9" />
  </TresMesh>
</template>
