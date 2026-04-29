<script setup lang="ts">
withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  accent?: string   // racing-stripe color
}>(), {
  rotation: () => [0, 0, 0],
  accent: '#a855f7',
})

const FABRIC = '#1a1d28'
const TRIM = '#2d3142'
const HARDWARE = '#0f1218'

// Geometry constants (chair sits on its wheels at y=0)
const WHEEL_R = 0.05
const SPOKE_R = 0.18
const SPOKE_LEN = 0.3

// Back panel
const BACK_Y = 1.15
const BACK_H = 0.85
const BACK_D = 0.15
const BACK_Z = 0.31
const BACK_OUTER = BACK_Z + BACK_D / 2 + 0.005  // racing stripe sits just outside the back

// Headrest
const HEAD_Y = 1.62
const HEAD_D = 0.16
const HEAD_OUTER = BACK_Z + HEAD_D / 2 + 0.005
</script>

<template>
  <TresGroup :position="position" :rotation="rotation">
    <!-- 5 spokes -->
    <TresMesh
      v-for="i in 5"
      :key="`spoke-${i}`"
      :position="[
        Math.cos((i - 1) * (Math.PI * 2 / 5)) * SPOKE_R,
        0.05,
        Math.sin((i - 1) * (Math.PI * 2 / 5)) * SPOKE_R,
      ]"
      :rotation="[0, -((i - 1) * (Math.PI * 2 / 5)) + Math.PI / 2, 0]"
    >
      <TresBoxGeometry :args="[SPOKE_LEN, 0.05, 0.07]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.4" :metalness="0.6" />
    </TresMesh>
    <!-- Wheels: spheres at the end of each spoke, sitting on the floor -->
    <TresMesh
      v-for="i in 5"
      :key="`wheel-${i}`"
      :position="[
        Math.cos((i - 1) * (Math.PI * 2 / 5)) * (SPOKE_R + SPOKE_LEN / 2 - WHEEL_R),
        WHEEL_R,
        Math.sin((i - 1) * (Math.PI * 2 / 5)) * (SPOKE_R + SPOKE_LEN / 2 - WHEEL_R),
      ]"
    >
      <TresSphereGeometry :args="[WHEEL_R, 12, 10]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.5" />
    </TresMesh>

    <!-- Pole -->
    <TresMesh :position="[0, 0.3, 0]">
      <TresCylinderGeometry :args="[0.04, 0.04, 0.4, 12]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.4" :metalness="0.6" />
    </TresMesh>
    <!-- Tilt plate -->
    <TresMesh :position="[0, 0.55, 0]">
      <TresBoxGeometry :args="[0.4, 0.05, 0.35]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.4" :metalness="0.6" />
    </TresMesh>

    <!-- Seat -->
    <TresMesh :position="[0, 0.65, 0]">
      <TresBoxGeometry :args="[0.7, 0.13, 0.7]" />
      <TresMeshStandardMaterial :color="FABRIC" :roughness="0.85" />
    </TresMesh>
    <!-- Side bolsters -->
    <TresMesh :position="[-0.3, 0.71, 0.05]">
      <TresBoxGeometry :args="[0.1, 0.15, 0.55]" />
      <TresMeshStandardMaterial :color="TRIM" :roughness="0.85" />
    </TresMesh>
    <TresMesh :position="[0.3, 0.71, 0.05]">
      <TresBoxGeometry :args="[0.1, 0.15, 0.55]" />
      <TresMeshStandardMaterial :color="TRIM" :roughness="0.85" />
    </TresMesh>

    <!-- Back panel -->
    <TresMesh :position="[0, BACK_Y, BACK_Z]">
      <TresBoxGeometry :args="[0.7, BACK_H, BACK_D]" />
      <TresMeshStandardMaterial :color="FABRIC" :roughness="0.85" />
    </TresMesh>
    <!-- Side wings -->
    <TresMesh :position="[-0.3, BACK_Y, BACK_Z + 0.01]">
      <TresBoxGeometry :args="[0.13, 0.78, 0.12]" />
      <TresMeshStandardMaterial :color="TRIM" :roughness="0.85" />
    </TresMesh>
    <TresMesh :position="[0.3, BACK_Y, BACK_Z + 0.01]">
      <TresBoxGeometry :args="[0.13, 0.78, 0.12]" />
      <TresMeshStandardMaterial :color="TRIM" :roughness="0.85" />
    </TresMesh>
    <!-- Racing stripe (on outside-back face, just outside the panel to avoid z-fighting) -->
    <TresMesh :position="[0, BACK_Y, BACK_OUTER]">
      <TresBoxGeometry :args="[0.15, 0.78, 0.01]" />
      <TresMeshBasicMaterial :color="accent" />
    </TresMesh>

    <!-- Headrest (overlaps top of back, dark trim color so it reads as part of the chair) -->
    <TresMesh :position="[0, HEAD_Y, BACK_Z]">
      <TresBoxGeometry :args="[0.42, 0.14, HEAD_D]" />
      <TresMeshStandardMaterial :color="TRIM" :roughness="0.85" />
    </TresMesh>
    <!-- Headrest accent line (outside face) -->
    <TresMesh :position="[0, HEAD_Y, HEAD_OUTER]">
      <TresBoxGeometry :args="[0.4, 0.035, 0.01]" />
      <TresMeshBasicMaterial :color="accent" />
    </TresMesh>

    <!-- Armrest brackets + pads -->
    <TresMesh :position="[-0.42, 0.78, 0]">
      <TresBoxGeometry :args="[0.06, 0.3, 0.08]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.5" :metalness="0.4" />
    </TresMesh>
    <TresMesh :position="[-0.42, 0.96, 0.05]">
      <TresBoxGeometry :args="[0.13, 0.05, 0.36]" />
      <TresMeshStandardMaterial :color="FABRIC" :roughness="0.85" />
    </TresMesh>
    <TresMesh :position="[0.42, 0.78, 0]">
      <TresBoxGeometry :args="[0.06, 0.3, 0.08]" />
      <TresMeshStandardMaterial :color="HARDWARE" :roughness="0.5" :metalness="0.4" />
    </TresMesh>
    <TresMesh :position="[0.42, 0.96, 0.05]">
      <TresBoxGeometry :args="[0.13, 0.05, 0.36]" />
      <TresMeshStandardMaterial :color="FABRIC" :roughness="0.85" />
    </TresMesh>
  </TresGroup>
</template>
