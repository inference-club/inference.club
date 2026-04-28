<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  size?: [number, number]   // frame width × height
}>(), {
  rotation: () => [0, 0, 0],
  size: () => [1.6, 1.2],
})

const { palette, isDark } = useScenePalette()
</script>

<template>
  <TresGroup :position="position" :rotation="rotation">
    <TresMesh>
      <TresBoxGeometry :args="[size[0], size[1], 0.05]" />
      <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.6" />
    </TresMesh>
    <TresMesh :position="[0, 0, 0.02]">
      <TresBoxGeometry :args="[size[0] - 0.2, size[1] - 0.2, 0.02]" />
      <TresMeshStandardMaterial
        :color="palette.windowGlass"
        :emissive="isDark ? '#3b6ea8' : '#000000'"
        :emissive-intensity="isDark ? 0.6 : 0"
      />
    </TresMesh>
  </TresGroup>
</template>
