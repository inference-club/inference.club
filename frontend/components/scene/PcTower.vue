<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  rgbColor?: string
  accentColor?: string  // secondary RGB color (cyan by default)
}>(), {
  rotation: () => [0, 0, 0],
  rgbColor: '#a855f7',
  accentColor: '#22d3ee',
})

const { palette } = useScenePalette()

// Case dimensions
const W = 0.65   // X (width)
const H = 1.15   // Y (height)
const D = 0.95   // Z (depth) — long enough to fit a full-length GPU
const WT = 0.025 // wall thickness

const HALF_PI = Math.PI / 2

// Internal palette — bright enough to read clearly through the open window.
const PCB_GREEN = '#2d5a3a'
const PCB_DARK = '#1a3a25'
const HEATSINK = '#5a6273'   // gunmetal — catches the eye through the glass
const HEATSINK_DARK = '#3a4252'
const SHROUD = '#2a2f38'
const FAN = '#1a1d24'
const FAN_HUB = '#0a0c12'
const RAM_BODY = '#4a5260'
</script>

<template>
  <TresGroup :position="position" :rotation="rotation">
    <!-- ============ Case shell — 5 walls; +X side is the window opening ============ -->
    <TresMesh :position="[0, -H / 2 + WT / 2, 0]">
      <TresBoxGeometry :args="[W, WT, D]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.25" />
    </TresMesh>
    <TresMesh :position="[0, H / 2 - WT / 2, 0]">
      <TresBoxGeometry :args="[W, WT, D]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.25" />
    </TresMesh>
    <TresMesh :position="[0, 0, D / 2 - WT / 2]">
      <TresBoxGeometry :args="[W, H, WT]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.25" />
    </TresMesh>
    <TresMesh :position="[0, 0, -D / 2 + WT / 2]">
      <TresBoxGeometry :args="[W, H, WT]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.25" />
    </TresMesh>
    <TresMesh :position="[-W / 2 + WT / 2, 0, 0]">
      <TresBoxGeometry :args="[WT, H, D]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.25" />
    </TresMesh>

    <!-- Window frame trim around the +X opening — reads as "tempered glass cutout" -->
    <TresMesh :position="[W / 2 - 0.005, H / 2 - 0.025, 0]">
      <TresBoxGeometry :args="[0.012, 0.05, D - 0.04]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.4" :metalness="0.5" />
    </TresMesh>
    <TresMesh :position="[W / 2 - 0.005, -H / 2 + 0.025, 0]">
      <TresBoxGeometry :args="[0.012, 0.05, D - 0.04]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.4" :metalness="0.5" />
    </TresMesh>
    <TresMesh :position="[W / 2 - 0.005, 0, D / 2 - 0.025]">
      <TresBoxGeometry :args="[0.012, H - 0.04, 0.05]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.4" :metalness="0.5" />
    </TresMesh>
    <TresMesh :position="[W / 2 - 0.005, 0, -D / 2 + 0.025]">
      <TresBoxGeometry :args="[0.012, H - 0.04, 0.05]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.4" :metalness="0.5" />
    </TresMesh>

    <!-- ============ Back-of-case RGB strip (top, runs along the inside back wall) ============ -->
    <TresMesh :position="[-W / 2 + WT + 0.008, H / 2 - WT - 0.025, 0]">
      <TresBoxGeometry :args="[0.005, 0.012, D - 0.1]" />
      <TresMeshBasicMaterial :color="rgbColor" />
    </TresMesh>
    <!-- Bottom interior RGB strip on the PSU shroud lip -->
    <TresMesh :position="[0, -H / 2 + WT + 0.18, D / 2 - WT - 0.015]">
      <TresBoxGeometry :args="[W - 2 * WT - 0.04, 0.008, 0.005]" />
      <TresMeshBasicMaterial :color="accentColor" />
    </TresMesh>

    <!-- ============ Motherboard PCB (full size, mounted on -X wall) ============ -->
    <TresMesh :position="[-W / 2 + WT + 0.014, 0.06, 0]">
      <TresBoxGeometry :args="[0.012, H - 0.34, D - 0.12]" />
      <TresMeshBasicMaterial :color="PCB_GREEN" />
    </TresMesh>
    <!-- Chipset heatsink (small dark square on motherboard) -->
    <TresMesh :position="[-W / 2 + WT + 0.027, -0.02, 0.06]">
      <TresBoxGeometry :args="[0.012, 0.07, 0.07]" />
      <TresMeshBasicMaterial :color="HEATSINK_DARK" />
    </TresMesh>
    <!-- M.2 / chipset trim accent -->
    <TresMesh :position="[-W / 2 + WT + 0.027, 0.04, -0.05]">
      <TresBoxGeometry :args="[0.008, 0.03, 0.13]" />
      <TresMeshBasicMaterial :color="HEATSINK" />
    </TresMesh>
    <!-- VRM heatsinks above CPU -->
    <TresMesh :position="[-W / 2 + WT + 0.025, 0.36, -0.03]">
      <TresBoxGeometry :args="[0.01, 0.06, 0.16]" />
      <TresMeshBasicMaterial :color="HEATSINK" />
    </TresMesh>

    <!-- ============ CPU air cooler (upper-middle of motherboard) ============ -->
    <TresGroup :position="[-W / 2 + WT + 0.13, 0.22, -0.05]">
      <!-- Tower body -->
      <TresMesh>
        <TresBoxGeometry :args="[0.18, 0.28, 0.18]" />
        <TresMeshBasicMaterial :color="HEATSINK" />
      </TresMesh>
      <!-- Horizontal fin lines (gives it that radiator look) -->
      <TresMesh
        v-for="i in 8"
        :key="`cooler-fin-${i}`"
        :position="[0, -0.135 + i * 0.03, 0]"
      >
        <TresBoxGeometry :args="[0.184, 0.005, 0.184]" />
        <TresMeshBasicMaterial :color="FAN" />
      </TresMesh>
      <!-- Top fan disc, visible head-on through the side window -->
      <TresMesh :position="[0.092, 0, 0]" :rotation="[0, 0, HALF_PI]">
        <TresCylinderGeometry :args="[0.078, 0.078, 0.005, 20]" />
        <TresMeshBasicMaterial :color="FAN" />
      </TresMesh>
      <!-- Glowing center hub on the fan -->
      <TresMesh :position="[0.094, 0, 0]" :rotation="[0, 0, HALF_PI]">
        <TresCylinderGeometry :args="[0.024, 0.024, 0.005, 16]" />
        <TresMeshBasicMaterial :color="rgbColor" />
      </TresMesh>
    </TresGroup>

    <!-- ============ RAM sticks (4 of them, RGB tops) ============ -->
    <TresMesh
      v-for="i in 4"
      :key="`ram-${i}`"
      :position="[-W / 2 + WT + 0.025, 0.21, -0.21 + (i - 1) * 0.025]"
    >
      <TresBoxGeometry :args="[0.018, 0.18, 0.014]" />
      <TresMeshBasicMaterial :color="RAM_BODY" />
    </TresMesh>
    <TresMesh
      v-for="i in 4"
      :key="`ram-rgb-${i}`"
      :position="[-W / 2 + WT + 0.026, 0.305, -0.21 + (i - 1) * 0.025]"
    >
      <TresBoxGeometry :args="[0.014, 0.008, 0.014]" />
      <TresMeshBasicMaterial :color="accentColor" />
    </TresMesh>

    <!-- ============ GPU — the centerpiece (long flagship card, 3 fans) ============ -->
    <!-- GPU PCB (thin strip behind the shroud) -->
    <TresMesh :position="[-W / 2 + WT + 0.045, -0.13, 0]">
      <TresBoxGeometry :args="[0.005, 0.05, 0.7]" />
      <TresMeshBasicMaterial :color="PCB_DARK" />
    </TresMesh>
    <!-- GPU shroud (chunky, visible broad face faces +X) -->
    <TresMesh :position="[-W / 2 + WT + 0.085, -0.09, 0]">
      <TresBoxGeometry :args="[0.075, 0.2, 0.7]" />
      <TresMeshBasicMaterial :color="SHROUD" />
    </TresMesh>
    <!-- Subtle shroud accent line (down the middle, full length) -->
    <TresMesh :position="[-W / 2 + WT + 0.124, -0.09, 0]">
      <TresBoxGeometry :args="[0.005, 0.012, 0.68]" />
      <TresMeshBasicMaterial :color="HEATSINK_DARK" />
    </TresMesh>
    <!-- GPU fans — three big discs spread along the length -->
    <TresMesh
      v-for="(z, idx) in [-0.22, 0, 0.22]"
      :key="`gpu-fan-${idx}`"
      :position="[-W / 2 + WT + 0.124, -0.09, z]"
      :rotation="[0, 0, HALF_PI]"
    >
      <TresCylinderGeometry :args="[0.085, 0.085, 0.005, 24]" />
      <TresMeshBasicMaterial :color="FAN" />
    </TresMesh>
    <!-- Fan blade hint: thin cross overlay per fan -->
    <TresMesh
      v-for="(z, idx) in [-0.22, 0, 0.22]"
      :key="`gpu-fan-cross-${idx}`"
      :position="[-W / 2 + WT + 0.126, -0.09, z]"
      :rotation="[0, 0, HALF_PI]"
    >
      <TresBoxGeometry :args="[0.005, 0.005, 0.16]" />
      <TresMeshBasicMaterial :color="HEATSINK_DARK" />
    </TresMesh>
    <!-- Fan hubs — RGB-lit centers -->
    <TresMesh
      v-for="(z, idx) in [-0.22, 0, 0.22]"
      :key="`gpu-fan-hub-${idx}`"
      :position="[-W / 2 + WT + 0.127, -0.09, z]"
      :rotation="[0, 0, HALF_PI]"
    >
      <TresCylinderGeometry :args="[0.02, 0.02, 0.005, 14]" />
      <TresMeshBasicMaterial :color="rgbColor" />
    </TresMesh>
    <!-- GPU brand RGB strip along the top edge of the shroud -->
    <TresMesh :position="[-W / 2 + WT + 0.124, 0.005, 0]">
      <TresBoxGeometry :args="[0.005, 0.01, 0.6]" />
      <TresMeshBasicMaterial :color="rgbColor" />
    </TresMesh>
    <!-- GPU support bracket at the front of the card -->
    <TresMesh :position="[-W / 2 + WT + 0.085, -0.21, 0.32]">
      <TresBoxGeometry :args="[0.075, 0.04, 0.012]" />
      <TresMeshBasicMaterial :color="HEATSINK_DARK" />
    </TresMesh>

    <!-- ============ PSU shroud across the bottom ============ -->
    <TresMesh :position="[0, -H / 2 + WT + 0.095, 0]">
      <TresBoxGeometry :args="[W - 2 * WT - 0.01, 0.18, D - 2 * WT - 0.01]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.6" :metalness="0.15" />
    </TresMesh>
    <!-- Cable management cutout: small dark slot -->
    <TresMesh :position="[-W / 2 + WT + 0.05, -H / 2 + WT + 0.18, 0.05]">
      <TresBoxGeometry :args="[0.012, 0.005, 0.18]" />
      <TresMeshBasicMaterial :color="FAN" />
    </TresMesh>

    <!-- ============ Front panel detail (+Z face) ============ -->
    <TresMesh
      :position="[0.18, 0.5, D / 2 - WT + 0.003]"
      :rotation="[HALF_PI, 0, 0]"
    >
      <TresCylinderGeometry :args="[0.018, 0.018, 0.005, 16]" />
      <TresMeshStandardMaterial :color="palette.pc" :roughness="0.4" :metalness="0.5" />
    </TresMesh>
    <TresMesh :position="[0.18, 0.55, D / 2 - WT + 0.005]">
      <TresBoxGeometry :args="[0.012, 0.012, 0.005]" />
      <TresMeshBasicMaterial color="#22c55e" />
    </TresMesh>
    <TresMesh :position="[0.18, 0.42, D / 2 - WT + 0.005]">
      <TresBoxGeometry :args="[0.06, 0.025, 0.005]" />
      <TresMeshBasicMaterial color="#0d1018" />
    </TresMesh>
    <!-- Front vertical RGB accent strip -->
    <TresMesh :position="[-W / 2 + 0.04, 0, D / 2 - WT + 0.005]">
      <TresBoxGeometry :args="[0.012, H - 0.18, 0.005]" />
      <TresMeshBasicMaterial :color="rgbColor" />
    </TresMesh>

    <!-- ============ Top vents ============ -->
    <TresMesh
      v-for="i in 8"
      :key="`vent-${i}`"
      :position="[0, H / 2 - WT + 0.002, -0.35 + (i - 1) * 0.1]"
    >
      <TresBoxGeometry :args="[W - 0.12, 0.005, 0.05]" />
      <TresMeshBasicMaterial :color="FAN" />
    </TresMesh>
  </TresGroup>
</template>
