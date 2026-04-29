<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeScreenTexture } from './textures'

const props = withDefaults(defineProps<{
  position: [number, number, number]
  primary: string
  secondary: string
  lidAngle?: number   // radians around X (negative = lid tilted back)
}>(), {
  lidAngle: -0.35,
})

const { palette, isDark } = useScenePalette()
const tex = shallowRef<THREE.CanvasTexture | null>(null)

const HALF_PI = Math.PI / 2

function build() {
  tex.value?.dispose()
  tex.value = makeScreenTexture({
    primary: props.primary,
    secondary: props.secondary,
    bg: isDark.value ? '#0b0218' : '#0b0b14',
    fg: isDark.value ? '#c084fc' : '#a855f7',
    sub: '#22d3ee',
  })
}

onMounted(() => {
  if (import.meta.client) build()
})
watch(isDark, () => {
  if (import.meta.client) build()
})
onBeforeUnmount(() => {
  tex.value?.dispose()
  tex.value = null
})
</script>

<template>
  <TresGroup :position="position">
    <!-- Base -->
    <TresMesh>
      <TresBoxGeometry :args="[1.3, 0.05, 0.9]" />
      <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
    </TresMesh>
    <!-- Keyboard slab -->
    <TresMesh :position="[0, 0.026, 0.05]" :rotation="[-HALF_PI, 0, 0]">
      <TresPlaneGeometry :args="[1.1, 0.6]" />
      <TresMeshBasicMaterial color="#1f2937" />
    </TresMesh>
    <!-- Lid -->
    <TresGroup :position="[0, 0.02, -0.45]" :rotation="[lidAngle, 0, 0]">
      <TresMesh :position="[0, 0.45, 0]">
        <TresBoxGeometry :args="[1.3, 0.9, 0.05]" />
        <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
      </TresMesh>
      <TresMesh :position="[0, 0.45, 0.026]">
        <TresPlaneGeometry :args="[1.18, 0.78]" />
        <TresMeshBasicMaterial :map="tex" :color="tex ? '#ffffff' : palette.logoText" />
      </TresMesh>
      <!-- Glow halo (dark mode) -->
      <TresMesh v-if="isDark" :position="[0, 0.45, -0.05]">
        <TresPlaneGeometry :args="[1.6, 1.1]" />
        <TresMeshBasicMaterial
          color="#a855f7"
          :transparent="true"
          :opacity="0.18"
          :blending="2"
          :depth-write="false"
        />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
