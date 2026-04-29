<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

withDefaults(defineProps<{
  position?: [number, number, number]
  size: [number, number]   // width × depth
}>(), {
  position: () => [0, 0, 0],
})

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Outer border -->
    <TresMesh :position="[0, 0.012, 0]">
      <TresBoxGeometry :args="[size[0], 0.02, size[1]]" />
      <TresMeshStandardMaterial :color="palette.bedroomRugBorder" :roughness="0.95" />
    </TresMesh>
    <!-- Inner field (slightly smaller, slightly raised so its edge shows) -->
    <TresMesh :position="[0, 0.024, 0]">
      <TresBoxGeometry :args="[size[0] - 0.3, 0.02, size[1] - 0.3]" />
      <TresMeshStandardMaterial :color="palette.bedroomRug" :roughness="0.95" />
    </TresMesh>
  </TresGroup>
</template>
