<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Cup -->
    <TresMesh :position="[0, 0.13, 0]">
      <TresCylinderGeometry :args="[0.13, 0.12, 0.26, 18]" />
      <TresMeshStandardMaterial :color="palette.mug" :roughness="0.5" />
    </TresMesh>
    <!-- Coffee surface -->
    <TresMesh :position="[0, 0.255, 0]">
      <TresCylinderGeometry :args="[0.115, 0.115, 0.01, 18]" />
      <TresMeshBasicMaterial :color="palette.mugInside" />
    </TresMesh>
  </TresGroup>
</template>
