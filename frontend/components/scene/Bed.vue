<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Frame -->
    <TresMesh :position="[0, 0.18, 0]">
      <TresBoxGeometry :args="[1.6, 0.36, 2.4]" />
      <TresMeshStandardMaterial :color="palette.roomAccent" :roughness="0.8" />
    </TresMesh>
    <!-- Blanket -->
    <TresMesh :position="[0, 0.46, 0.15]">
      <TresBoxGeometry :args="[1.45, 0.22, 2.0]" />
      <TresMeshStandardMaterial :color="palette.blanket" :roughness="0.9" />
    </TresMesh>
    <!-- Pillow -->
    <TresMesh :position="[0, 0.62, -0.78]">
      <TresBoxGeometry :args="[1.2, 0.18, 0.45]" />
      <TresMeshStandardMaterial :color="palette.pillow" :roughness="0.95" />
    </TresMesh>
  </TresGroup>
</template>
