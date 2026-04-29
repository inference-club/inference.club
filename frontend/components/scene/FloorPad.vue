<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

const props = withDefaults(defineProps<{
  position?: [number, number, number]
  size: [number, number]   // width × depth
  height?: number
  bevel?: boolean
}>(), {
  position: () => [0, 0, 0],
  height: 0.3,
  bevel: false,
})

const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="props.position">
    <TresMesh :position="[0, -height / 2, 0]">
      <TresBoxGeometry :args="[size[0], height, size[1]]" />
      <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
    </TresMesh>
    <TresMesh v-if="bevel" :position="[0, -height - 0.025, 0]">
      <TresBoxGeometry :args="[size[0] - 0.2, 0.05, size[1] - 0.2]" />
      <TresMeshStandardMaterial :color="palette.floorBevel" :roughness="0.85" />
    </TresMesh>
  </TresGroup>
</template>
