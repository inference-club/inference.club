<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Headboard (head end is -Z; rises behind the pillow) -->
    <TresMesh :position="[0, 0.85, -1.22]">
      <TresBoxGeometry :args="[1.7, 1.3, 0.08]" />
      <TresMeshStandardMaterial :color="palette.roomAccent" :roughness="0.8" />
    </TresMesh>
    <!-- Headboard top trim -->
    <TresMesh :position="[0, 1.52, -1.22]">
      <TresBoxGeometry :args="[1.75, 0.06, 0.12]" />
      <TresMeshStandardMaterial :color="palette.deskDark" :roughness="0.7" />
    </TresMesh>
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
