<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeScreenTexture } from './textures'

defineProps<{
  position: [number, number, number]
}>()

const { palette, isDark } = useScenePalette()
const monitorTex = shallowRef<THREE.CanvasTexture | null>(null)

const HALF_PI = Math.PI / 2

function buildMonitorTex() {
  monitorTex.value?.dispose()
  monitorTex.value = makeScreenTexture({
    primary: 'vLLM',
    secondary: 'MODEL LOADED',
    bg: isDark.value ? '#000814' : '#0b0b14',
    fg: '#ffffff',
    sub: '#22c55e',
  })
}

onMounted(() => {
  if (!import.meta.client) return
  buildMonitorTex()
})

watch(isDark, () => {
  if (!import.meta.client) return
  buildMonitorTex()
})

onBeforeUnmount(() => {
  monitorTex.value?.dispose()
  monitorTex.value = null
})
</script>

<template>
  <TresGroup :position="position">
    <!-- Floor pad -->
    <TresMesh :position="[0, -0.15, 0]">
      <TresBoxGeometry :args="[6, 0.3, 5]" />
      <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
    </TresMesh>

    <!-- Walls -->
    <TresMesh :position="[0, 1.55, -2.45]">
      <TresBoxGeometry :args="[6, 3.4, 0.15]" />
      <TresMeshStandardMaterial :color="palette.wall" :roughness="0.9" />
    </TresMesh>
    <TresMesh :position="[-2.95, 1.55, 0]">
      <TresBoxGeometry :args="[0.15, 3.4, 5]" />
      <TresMeshStandardMaterial :color="palette.wall" :roughness="0.9" />
    </TresMesh>

    <!-- Window -->
    <TresMesh :position="[1.4, 2.0, -2.36]">
      <TresBoxGeometry :args="[1.6, 1.2, 0.05]" />
      <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.6" />
    </TresMesh>
    <TresMesh :position="[1.4, 2.0, -2.34]">
      <TresBoxGeometry :args="[1.4, 1.0, 0.02]" />
      <TresMeshStandardMaterial
        :color="palette.windowGlass"
        :emissive="isDark ? '#3b6ea8' : '#000000'"
        :emissive-intensity="isDark ? 0.6 : 0"
      />
    </TresMesh>

    <!-- Picture -->
    <TresMesh :position="[-2.86, 2.1, 1.0]" :rotation="[0, HALF_PI, 0]">
      <TresBoxGeometry :args="[0.7, 0.55, 0.03]" />
      <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.5" />
    </TresMesh>
    <TresMesh :position="[-2.84, 2.1, 1.0]" :rotation="[0, HALF_PI, 0]">
      <TresBoxGeometry :args="[0.6, 0.45, 0.02]" />
      <TresMeshBasicMaterial :color="palette.pictureArt" />
    </TresMesh>

    <!-- Bed -->
    <TresGroup :position="[-1.6, 0, 1.3]">
      <TresMesh :position="[0, 0.18, 0]">
        <TresBoxGeometry :args="[1.6, 0.36, 2.4]" />
        <TresMeshStandardMaterial :color="palette.roomAccent" :roughness="0.8" />
      </TresMesh>
      <TresMesh :position="[0, 0.46, 0.15]">
        <TresBoxGeometry :args="[1.45, 0.22, 2.0]" />
        <TresMeshStandardMaterial :color="palette.blanket" :roughness="0.9" />
      </TresMesh>
      <TresMesh :position="[0, 0.62, -0.78]">
        <TresBoxGeometry :args="[1.2, 0.18, 0.45]" />
        <TresMeshStandardMaterial :color="palette.pillow" :roughness="0.95" />
      </TresMesh>
    </TresGroup>

    <!-- Desk + monitor + PC -->
    <TresGroup :position="[1.0, 0, -1.0]">
      <TresMesh :position="[0, 1.0, 0]">
        <TresBoxGeometry :args="[2.6, 0.08, 1.2]" />
        <TresMeshStandardMaterial :color="palette.desk" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[-1.2, 0.5, -0.5]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial :color="palette.deskDark" />
      </TresMesh>
      <TresMesh :position="[1.2, 0.5, -0.5]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial :color="palette.deskDark" />
      </TresMesh>
      <TresMesh :position="[-1.2, 0.5, 0.5]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial :color="palette.deskDark" />
      </TresMesh>
      <TresMesh :position="[1.2, 0.5, 0.5]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial :color="palette.deskDark" />
      </TresMesh>

      <!-- Monitor -->
      <TresMesh :position="[-0.5, 1.18, -0.45]">
        <TresBoxGeometry :args="[0.5, 0.05, 0.3]" />
        <TresMeshStandardMaterial :color="palette.screenBezel" />
      </TresMesh>
      <TresMesh :position="[-0.5, 1.4, -0.42]">
        <TresBoxGeometry :args="[0.06, 0.4, 0.06]" />
        <TresMeshStandardMaterial :color="palette.screenBezel" />
      </TresMesh>
      <TresGroup :position="[-0.5, 1.85, -0.4]" :rotation="[0.05, 0, 0]">
        <TresMesh :position="[0, 0, 0]">
          <TresBoxGeometry :args="[1.4, 0.85, 0.06]" />
          <TresMeshStandardMaterial :color="palette.screenBezel" :roughness="0.5" />
        </TresMesh>
        <TresMesh :position="[0, 0, 0.04]">
          <TresPlaneGeometry :args="[1.28, 0.74]" />
          <TresMeshBasicMaterial :map="monitorTex" :color="monitorTex ? '#ffffff' : '#22c55e'" />
        </TresMesh>
        <TresMesh v-if="isDark" :position="[0, 0, -0.05]">
          <TresPlaneGeometry :args="[1.7, 1.1]" />
          <TresMeshBasicMaterial
            color="#22c55e"
            :transparent="true"
            :opacity="0.15"
            :blending="2"
            :depth-write="false"
          />
        </TresMesh>
      </TresGroup>

      <!-- PC tower -->
      <TresGroup :position="[1.0, 1.55, -0.35]">
        <TresMesh :position="[0, 0, 0]">
          <TresBoxGeometry :args="[0.55, 1.0, 0.55]" />
          <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.2" />
        </TresMesh>
        <TresMesh :position="[0, -0.1, 0.276]">
          <TresPlaneGeometry :args="[0.42, 0.22]" />
          <TresMeshBasicMaterial :color="palette.pcAccent" />
        </TresMesh>
        <TresMesh :position="[-0.18, 0.4, 0.276]">
          <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
          <TresMeshBasicMaterial color="#22c55e" />
        </TresMesh>
        <TresMesh :position="[0.0, 0.4, 0.276]">
          <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
          <TresMeshBasicMaterial color="#a855f7" />
        </TresMesh>
      </TresGroup>
    </TresGroup>

    <!-- Office chair -->
    <TresGroup :position="[1.2, 0, 0.6]">
      <TresMesh :position="[0, 0.55, 0]">
        <TresBoxGeometry :args="[0.7, 0.08, 0.7]" />
        <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[0, 0.95, 0.32]">
        <TresBoxGeometry :args="[0.65, 0.7, 0.08]" />
        <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[0, 0.27, 0]">
        <TresCylinderGeometry :args="[0.05, 0.05, 0.5, 12]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[0, 0.04, 0]">
        <TresCylinderGeometry :args="[0.4, 0.4, 0.05, 16]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
