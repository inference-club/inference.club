<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  size?: [number, number]   // frame width × height
}>(), {
  rotation: () => [0, 0, 0],
  size: () => [0.7, 0.55],
})

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position" :rotation="rotation">
    <TresMesh>
      <TresBoxGeometry :args="[size[0], size[1], 0.03]" />
      <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.5" />
    </TresMesh>
    <TresMesh :position="[0, 0, 0.02]">
      <TresBoxGeometry :args="[size[0] - 0.1, size[1] - 0.1, 0.02]" />
      <TresMeshBasicMaterial :color="palette.pictureArt" />
    </TresMesh>
  </TresGroup>
</template>
