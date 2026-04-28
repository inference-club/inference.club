<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

const props = withDefaults(defineProps<{
  position?: [number, number, number]
  size: [number, number, number]   // width × top thickness × depth
  height?: number                   // distance from floor to top of desk
  topColor?: string
  legColor?: string
  legThickness?: number
}>(), {
  position: () => [0, 0, 0],
  height: 1.0,
  topColor: undefined,
  legColor: undefined,
  legThickness: 0.08,
})

const { palette } = useScenePalette()

const inset = 0.1
const xOff = props.size[0] / 2 - inset
const zOff = props.size[2] / 2 - inset
const legY = (props.height - props.size[1]) / 2
const legHeight = props.height - props.size[1]
</script>

<template>
  <TresGroup :position="props.position">
    <TresMesh :position="[0, height, 0]">
      <TresBoxGeometry :args="size" />
      <TresMeshStandardMaterial :color="topColor ?? palette.desk" :roughness="0.7" />
    </TresMesh>
    <TresMesh
      v-for="[x, z] in [[-xOff, -zOff], [xOff, -zOff], [-xOff, zOff], [xOff, zOff]]"
      :key="`leg-${x}-${z}`"
      :position="[x, legY, z]"
    >
      <TresBoxGeometry :args="[legThickness, legHeight, legThickness]" />
      <TresMeshStandardMaterial :color="legColor ?? palette.deskDark" />
    </TresMesh>
  </TresGroup>
</template>
