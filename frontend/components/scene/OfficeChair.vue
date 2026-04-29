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
      <TresBoxGeometry :args="[0.7, 0.08, 0.7]" />
      <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
    </TresMesh>
    <!-- Backrest -->
    <TresMesh :position="[0, 0.95, 0.32]">
      <TresBoxGeometry :args="[0.65, 0.7, 0.08]" />
      <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
    </TresMesh>
    <!-- Pole -->
    <TresMesh :position="[0, 0.27, 0]">
      <TresCylinderGeometry :args="[0.05, 0.05, 0.5, 12]" />
      <TresMeshStandardMaterial color="#1f2937" />
    </TresMesh>
    <!-- Wheelbase -->
    <TresMesh :position="[0, 0.04, 0]">
      <TresCylinderGeometry :args="[0.4, 0.4, 0.05, 16]" />
      <TresMeshStandardMaterial color="#1f2937" />
    </TresMesh>
  </TresGroup>
</template>
