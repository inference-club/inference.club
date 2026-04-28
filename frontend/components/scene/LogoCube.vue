<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeLogoTexture } from './textures'

withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  size?: number
}>(), {
  rotation: () => [0, -0.35, 0],
  size: 0.95,
})

const { palette, isDark } = useScenePalette()
const tex = shallowRef<THREE.CanvasTexture | null>(null)

function build() {
  tex.value?.dispose()
  tex.value = makeLogoTexture(
    isDark.value ? '#0a0a16' : '#ffffff',
    isDark.value ? '#a5b4fc' : '#6366f1',
  )
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
  <TresGroup :position="position" :rotation="rotation">
    <TresMesh>
      <TresBoxGeometry :args="[size, size, size]" />
      <TresMeshStandardMaterial
        :color="palette.logoWhite"
        :roughness="0.55"
        :emissive="isDark ? '#6366f1' : '#000000'"
        :emissive-intensity="isDark ? 0.25 : 0"
      />
    </TresMesh>
    <TresMesh :position="[0, 0, size / 2 + 0.005]">
      <TresPlaneGeometry :args="[size * 0.9, size * 0.9]" />
      <TresMeshBasicMaterial :map="tex" :color="tex ? '#ffffff' : palette.logoText" />
    </TresMesh>
  </TresGroup>
</template>
