<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import { makeScreenTexture } from './textures'

defineProps<{
  position: [number, number, number]
}>()

const { palette, isDark } = useScenePalette()
const laptopTex = shallowRef<THREE.CanvasTexture | null>(null)

const HALF_PI = Math.PI / 2

function buildLaptopTex() {
  laptopTex.value?.dispose()
  laptopTex.value = makeScreenTexture({
    primary: 'inference.club',
    secondary: 'CONNECTING...',
    bg: isDark.value ? '#0b0218' : '#0b0b14',
    fg: isDark.value ? '#c084fc' : '#a855f7',
    sub: '#22d3ee',
  })
}

onMounted(() => {
  if (!import.meta.client) return
  buildLaptopTex()
})

watch(isDark, () => {
  if (!import.meta.client) return
  buildLaptopTex()
})

onBeforeUnmount(() => {
  laptopTex.value?.dispose()
  laptopTex.value = null
})
</script>

<template>
  <TresGroup :position="position">
    <!-- Floor pad -->
    <TresMesh :position="[0, -0.15, 0]">
      <TresBoxGeometry :args="[5, 0.3, 4]" />
      <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
    </TresMesh>

    <TresGroup :position="[0, 0, 0]">
      <!-- Desk -->
      <TresMesh :position="[0, 1.05, 0]">
        <TresBoxGeometry :args="[3.0, 0.1, 1.6]" />
        <TresMeshStandardMaterial :color="palette.desk" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[-1.4, 0.55, -0.7]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[1.4, 0.55, -0.7]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[-1.4, 0.55, 0.7]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[1.4, 0.55, 0.7]">
        <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>

      <!-- Laptop -->
      <TresGroup :position="[-0.2, 1.12, -0.05]">
        <!-- Base -->
        <TresMesh :position="[0, 0, 0]">
          <TresBoxGeometry :args="[1.3, 0.05, 0.9]" />
          <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
        </TresMesh>
        <!-- Keyboard slab -->
        <TresMesh :position="[0, 0.026, 0.05]" :rotation="[-HALF_PI, 0, 0]">
          <TresPlaneGeometry :args="[1.1, 0.6]" />
          <TresMeshBasicMaterial color="#1f2937" />
        </TresMesh>
        <!-- Lid (screen) -->
        <TresGroup :position="[0, 0.02, -0.45]" :rotation="[-0.35, 0, 0]">
          <TresMesh :position="[0, 0.45, 0]">
            <TresBoxGeometry :args="[1.3, 0.9, 0.05]" />
            <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
          </TresMesh>
          <TresMesh :position="[0, 0.45, 0.026]">
            <TresPlaneGeometry :args="[1.18, 0.78]" />
            <TresMeshBasicMaterial :map="laptopTex" :color="laptopTex ? '#ffffff' : palette.logoText" />
          </TresMesh>
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

      <!-- Plant -->
      <TresGroup :position="[1.15, 1.1, 0.0]">
        <TresMesh :position="[0, 0.15, 0]">
          <TresCylinderGeometry :args="[0.18, 0.14, 0.3, 16]" />
          <TresMeshStandardMaterial :color="palette.plantPot" :roughness="0.85" />
        </TresMesh>
        <TresMesh :position="[0, 0.45, 0]">
          <TresIcosahedronGeometry :args="[0.28, 0]" />
          <TresMeshStandardMaterial :color="palette.plantLeaves" :roughness="0.8" />
        </TresMesh>
        <TresMesh :position="[0.15, 0.6, 0.05]">
          <TresIcosahedronGeometry :args="[0.18, 0]" />
          <TresMeshStandardMaterial :color="palette.plantLeavesAlt" :roughness="0.8" />
        </TresMesh>
      </TresGroup>

      <!-- Coffee mug -->
      <TresGroup :position="[1.1, 1.1, 0.55]">
        <TresMesh :position="[0, 0.13, 0]">
          <TresCylinderGeometry :args="[0.13, 0.12, 0.26, 18]" />
          <TresMeshStandardMaterial :color="palette.mug" :roughness="0.5" />
        </TresMesh>
        <TresMesh :position="[0, 0.255, 0]">
          <TresCylinderGeometry :args="[0.115, 0.115, 0.01, 18]" />
          <TresMeshBasicMaterial :color="palette.mugInside" />
        </TresMesh>
      </TresGroup>
    </TresGroup>

    <!-- Chair -->
    <TresGroup :position="[-0.2, 0, 1.4]">
      <TresMesh :position="[0, 0.55, 0]">
        <TresBoxGeometry :args="[0.8, 0.08, 0.7]" />
        <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[0, 1.0, 0.34]">
        <TresBoxGeometry :args="[0.8, 0.85, 0.08]" />
        <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
      </TresMesh>
      <TresMesh :position="[-0.32, 0.27, -0.3]">
        <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[0.32, 0.27, -0.3]">
        <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[-0.32, 0.27, 0.3]">
        <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
      <TresMesh :position="[0.32, 0.27, 0.3]">
        <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
        <TresMeshStandardMaterial color="#1f2937" />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
