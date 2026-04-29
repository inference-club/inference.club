<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeScreenTexture } from './textures'

const props = withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  primary: string
  secondary: string
  fg?: string
  sub?: string
}>(), {
  rotation: () => [0, 0, 0],
  fg: '#ffffff',
  sub: '#22c55e',
})

const { palette, isDark } = useScenePalette()
const tex = shallowRef<THREE.CanvasTexture | null>(null)

function build() {
  tex.value?.dispose()
  tex.value = makeScreenTexture({
    primary: props.primary,
    secondary: props.secondary,
    bg: isDark.value ? '#000814' : '#0b0b14',
    fg: props.fg ?? '#ffffff',
    sub: props.sub ?? '#22c55e',
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
  <TresGroup :position="position" :rotation="rotation">
    <!-- y=0 is the bottom of the stand base, so the caller can pass the
         desk-top point as `position` and the monitor stands flush on it. -->
    <TresMesh :position="[0, 0.025, -0.05]">
      <TresBoxGeometry :args="[0.5, 0.05, 0.3]" />
      <TresMeshStandardMaterial :color="palette.screenBezel" />
    </TresMesh>
    <TresMesh :position="[0, 0.245, -0.02]">
      <TresBoxGeometry :args="[0.06, 0.4, 0.06]" />
      <TresMeshStandardMaterial :color="palette.screenBezel" />
    </TresMesh>
    <TresGroup :position="[0, 0.695, 0]" :rotation="[0.05, 0, 0]">
      <TresMesh>
        <TresBoxGeometry :args="[1.4, 0.85, 0.06]" />
        <TresMeshStandardMaterial :color="palette.screenBezel" :roughness="0.5" />
      </TresMesh>
      <TresMesh :position="[0, 0, 0.04]">
        <TresPlaneGeometry :args="[1.28, 0.74]" />
        <TresMeshBasicMaterial :map="tex" :color="tex ? '#ffffff' : sub" />
      </TresMesh>
      <TresMesh v-if="isDark" :position="[0, 0, -0.05]">
        <TresPlaneGeometry :args="[1.7, 1.1]" />
        <TresMeshBasicMaterial
          :color="sub"
          :transparent="true"
          :opacity="0.15"
          :blending="2"
          :depth-write="false"
        />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
