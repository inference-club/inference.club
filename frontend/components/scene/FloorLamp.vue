<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const { palette, isDark } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <!-- Base disc -->
    <TresMesh :position="[0, 0.04, 0]">
      <TresCylinderGeometry :args="[0.25, 0.28, 0.08, 24]" />
      <TresMeshStandardMaterial :color="palette.lampPole" :roughness="0.5" :metalness="0.6" />
    </TresMesh>
    <!-- Pole -->
    <TresMesh :position="[0, 1.3, 0]">
      <TresCylinderGeometry :args="[0.03, 0.03, 2.5, 12]" />
      <TresMeshStandardMaterial :color="palette.lampPole" :roughness="0.4" :metalness="0.7" />
    </TresMesh>
    <!-- Shade (truncated cone) -->
    <TresMesh :position="[0, 2.7, 0]">
      <TresCylinderGeometry :args="[0.32, 0.45, 0.5, 24, 1, true]" />
      <TresMeshStandardMaterial
        :color="palette.lampShade"
        :roughness="0.8"
        :side="2"
        :emissive="isDark ? palette.lampShade : '#000000'"
        :emissive-intensity="isDark ? 0.9 : 0"
      />
    </TresMesh>
    <!-- Bulb glow disc on the underside (only visible from below in dark) -->
    <TresMesh v-if="isDark" :position="[0, 2.46, 0]" :rotation="[Math.PI / 2, 0, 0]">
      <TresCircleGeometry :args="[0.42, 24]" />
      <TresMeshBasicMaterial
        :color="palette.lampShade"
        :transparent="true"
        :opacity="0.6"
      />
    </TresMesh>
    <!-- Cast light into the room (dark mode only) -->
    <TresPointLight
      :position="[0, 2.5, 0]"
      :intensity="isDark ? 18 : 0"
      :distance="6"
      :decay="2"
      color="#ffd28a"
    />
  </TresGroup>
</template>
