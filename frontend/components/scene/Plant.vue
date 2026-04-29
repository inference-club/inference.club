<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Pot -->
    <TresMesh :position="[0, 0.15, 0]">
      <TresCylinderGeometry :args="[0.18, 0.14, 0.3, 16]" />
      <TresMeshStandardMaterial :color="palette.plantPot" :roughness="0.85" />
    </TresMesh>
    <!-- Foliage -->
    <TresMesh :position="[0, 0.45, 0]">
      <TresIcosahedronGeometry :args="[0.28, 0]" />
      <TresMeshStandardMaterial :color="palette.plantLeaves" :roughness="0.8" />
    </TresMesh>
    <TresMesh :position="[0.15, 0.6, 0.05]">
      <TresIcosahedronGeometry :args="[0.18, 0]" />
      <TresMeshStandardMaterial :color="palette.plantLeavesAlt" :roughness="0.8" />
    </TresMesh>
  </TresGroup>
</template>
