<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Body -->
    <TresMesh :position="[0, 0.85, 0]">
      <TresBoxGeometry :args="[1.3, 1.7, 1.2]" />
      <TresMeshStandardMaterial :color="palette.serverBody" :roughness="0.4" :metalness="0.3" />
    </TresMesh>
    <!-- Slot lines -->
    <TresMesh
      v-for="i in 4"
      :key="`slot-${i}`"
      :position="[0, 0.25 + i * 0.3, 0.61]"
    >
      <TresBoxGeometry :args="[1.1, 0.04, 0.02]" />
      <TresMeshStandardMaterial :color="palette.serverSlot" />
    </TresMesh>
    <!-- LEDs -->
    <TresMesh
      v-for="i in 4"
      :key="`led-${i}`"
      :position="[0.47, 0.25 + i * 0.3, 0.62]"
    >
      <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
      <TresMeshBasicMaterial :color="palette.serverAccent" />
    </TresMesh>
  </TresGroup>
</template>
