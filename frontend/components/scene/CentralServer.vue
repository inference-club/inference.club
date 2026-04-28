<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeLogoTexture } from './textures'

defineProps<{
  position: [number, number, number]
}>()

const { palette, isDark } = useScenePalette()
const logoTex = shallowRef<THREE.CanvasTexture | null>(null)

function buildLogoTex() {
  logoTex.value?.dispose()
  logoTex.value = makeLogoTexture(
    isDark.value ? '#0a0a16' : '#ffffff',
    isDark.value ? '#a5b4fc' : '#6366f1',
  )
}

onMounted(() => {
  if (!import.meta.client) return
  buildLogoTex()
})

watch(isDark, () => {
  if (!import.meta.client) return
  buildLogoTex()
})

onBeforeUnmount(() => {
  logoTex.value?.dispose()
  logoTex.value = null
})
</script>

<template>
  <TresGroup :position="position">
    <!-- Pad -->
    <TresMesh :position="[0, -0.15, 0]">
      <TresBoxGeometry :args="[3.6, 0.3, 3.0]" />
      <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
    </TresMesh>
    <TresMesh :position="[0, -0.32, 0]">
      <TresBoxGeometry :args="[3.4, 0.05, 2.8]" />
      <TresMeshStandardMaterial :color="palette.floorBevel" :roughness="0.85" />
    </TresMesh>

    <!-- Server rack -->
    <TresGroup :position="[-0.45, 0, -0.1]">
      <TresMesh :position="[0, 0.85, 0]">
        <TresBoxGeometry :args="[1.3, 1.7, 1.2]" />
        <TresMeshStandardMaterial :color="palette.serverBody" :roughness="0.4" :metalness="0.3" />
      </TresMesh>
      <TresMesh
        v-for="i in 4"
        :key="`slot-${i}`"
        :position="[0, 0.25 + i * 0.3, 0.61]"
      >
        <TresBoxGeometry :args="[1.1, 0.04, 0.02]" />
        <TresMeshStandardMaterial :color="palette.serverSlot" />
      </TresMesh>
      <TresMesh
        v-for="i in 4"
        :key="`led-${i}`"
        :position="[0.47, 0.25 + i * 0.3, 0.62]"
      >
        <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
        <TresMeshBasicMaterial :color="palette.serverAccent" />
      </TresMesh>
    </TresGroup>

    <!-- Logo cube -->
    <TresGroup :position="[0.85, 0.55, 0.55]" :rotation="[0, -0.35, 0]">
      <TresMesh>
        <TresBoxGeometry :args="[0.95, 0.95, 0.95]" />
        <TresMeshStandardMaterial
          :color="palette.logoWhite"
          :roughness="0.55"
          :emissive="isDark ? '#6366f1' : '#000000'"
          :emissive-intensity="isDark ? 0.25 : 0"
        />
      </TresMesh>
      <TresMesh :position="[0, 0, 0.476]">
        <TresPlaneGeometry :args="[0.85, 0.85]" />
        <TresMeshBasicMaterial :map="logoTex" :color="logoTex ? '#ffffff' : palette.logoText" />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
