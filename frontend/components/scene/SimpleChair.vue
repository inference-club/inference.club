<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Seat -->
    <TresMesh :position="[0, 0.55, 0]">
      <TresBoxGeometry :args="[0.8, 0.08, 0.7]" />
      <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
    </TresMesh>
    <!-- Backrest -->
    <TresMesh :position="[0, 1.0, 0.34]">
      <TresBoxGeometry :args="[0.8, 0.85, 0.08]" />
      <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
    </TresMesh>
    <!-- Legs -->
    <TresMesh
      v-for="[x, z] in [[-0.32, -0.3], [0.32, -0.3], [-0.32, 0.3], [0.32, 0.3]]"
      :key="`leg-${x}-${z}`"
      :position="[x, 0.27, z]"
    >
      <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
      <TresMeshStandardMaterial color="#1f2937" />
    </TresMesh>
  </TresGroup>
</template>
