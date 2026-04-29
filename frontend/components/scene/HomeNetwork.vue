<script setup lang="ts">
import { useScenePalette } from '@/composables/useScenePalette'

defineProps<{
  position: [number, number, number]
}>()

const HALF_PI = Math.PI / 2
const { palette } = useScenePalette()
</script>

<template>
  <TresGroup :position="position">
    <SceneFloorPad :size="[6, 5]" />

    <!-- Walls (bedroom paint color) -->
    <SceneWall :position="[0, 1.55, -2.45]" :size="[6, 3.4, 0.15]" :color="palette.bedroomWall" />
    <SceneWall :position="[-2.95, 1.55, 0]" :size="[0.15, 3.4, 5]" :color="palette.bedroomWall" />

    <!-- Window + framed picture -->
    <SceneWindow :position="[1.4, 2.0, -2.36]" />
    <ScenePicture :position="[-2.86, 2.1, 1.0]" :rotation="[0, HALF_PI, 0]" />

    <!-- Posters: back wall over the bed + above the desk -->
    <ScenePoster
      :position="[-1.6, 1.8, -2.36]"
      :size="[0.95, 1.3]"
      variant="sun"
      color1="#0f172a"
      color2="#f97316"
      color3="#fde68a"
    />
    <ScenePoster
      :position="[-0.3, 1.95, -2.36]"
      :size="[0.7, 0.95]"
      variant="gradient"
      color1="#7c3aed"
      color2="#22d3ee"
    />
    <ScenePoster
      :position="[0.45, 1.05, -2.36]"
      :size="[0.55, 0.75]"
      variant="stripes"
      color1="#0f172a"
      color2="#f59e0b"
      color3="#ef4444"
    />
    <!-- Posters on side wall above the framed picture -->
    <ScenePoster
      :position="[-2.86, 2.55, -0.4]"
      :rotation="[0, HALF_PI, 0]"
      :size="[0.6, 0.85]"
      variant="split"
      color1="#1e293b"
      color2="#22c55e"
    />

    <!-- Rug under the desk + chair area -->
    <SceneRug :position="[1.0, 0, 0.3]" :size="[3.4, 2.6]" />

    <!-- Bed against back wall (head end at z = -2.3) -->
    <SceneBed :position="[-1.6, 0, -1.1]" />

    <!-- Floor lamp in the back-left corner -->
    <SceneFloorLamp :position="[-2.3, 0, -1.8]" />

    <!-- Desk + monitor + PC tower -->
    <TresGroup :position="[1.0, 0, -1.0]">
      <SceneDesk :size="[2.6, 0.08, 1.2]" :height="1.0" />
      <SceneMonitor
        :position="[-0.5, 1.04, -0.4]"
        primary="vLLM"
        secondary="MODEL LOADED"
      />
      <ScenePcTower :position="[1.0, 1.615, -0.125]" />
    </TresGroup>

    <!-- Gamer chair at the desk (lifted onto the rug top, back panel facing camera) -->
    <SceneGamerChair :position="[1.2, 0.034, 0.6]" />
  </TresGroup>
</template>
