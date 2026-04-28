<script setup lang="ts">
defineProps<{
  position: [number, number, number]
}>()

const HALF_PI = Math.PI / 2
</script>

<template>
  <TresGroup :position="position">
    <SceneFloorPad :size="[6, 5]" />

    <SceneWall :position="[0, 1.55, -2.45]" :size="[6, 3.4, 0.15]" />
    <SceneWall :position="[-2.95, 1.55, 0]" :size="[0.15, 3.4, 5]" />

    <SceneWindow :position="[1.4, 2.0, -2.36]" />
    <ScenePicture
      :position="[-2.86, 2.1, 1.0]"
      :rotation="[0, HALF_PI, 0]"
    />

    <SceneBed :position="[-1.6, 0, 1.3]" />

    <!-- Desk + monitor + PC tower -->
    <TresGroup :position="[1.0, 0, -1.0]">
      <SceneDesk :size="[2.6, 0.08, 1.2]" :height="1.0" />
      <SceneMonitor
        :position="[-0.5, 1.85, -0.4]"
        primary="vLLM"
        secondary="MODEL LOADED"
      />
      <ScenePcTower :position="[1.0, 1.55, -0.35]" />
    </TresGroup>

    <SceneOfficeChair :position="[1.2, 0, 0.6]" />
  </TresGroup>
</template>
