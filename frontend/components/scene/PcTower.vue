<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Case -->
    <TresMesh>
      <TresBoxGeometry :args="[0.55, 1.0, 0.55]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.2" />
    </TresMesh>
    <!-- GPU label face -->
    <TresMesh :position="[0, -0.1, 0.276]">
      <TresPlaneGeometry :args="[0.42, 0.22]" />
      <TresMeshBasicMaterial :color="palette.pcAccent" />
    </TresMesh>
    <!-- LEDs -->
    <TresMesh :position="[-0.18, 0.4, 0.276]">
      <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
      <TresMeshBasicMaterial color="#22c55e" />
    </TresMesh>
    <TresMesh :position="[0, 0.4, 0.276]">
      <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
      <TresMeshBasicMaterial color="#a855f7" />
    </TresMesh>
  </TresGroup>
</template>
