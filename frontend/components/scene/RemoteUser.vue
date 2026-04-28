<script setup lang="ts">
defineProps<{
  position: [number, number, number]
}>()
</script>

<template>
  <TresGroup :position="position">
    <SceneFloorPad :size="[5, 4]" />

    <!-- Desk + everything on it -->
    <TresGroup :position="[0, 0, 0]">
      <SceneDesk
        :size="[3.0, 0.1, 1.6]"
        :height="1.05"
        leg-color="#1f2937"
      />
      <SceneLaptop
        :position="[-0.2, 1.12, -0.05]"
        primary="inference.club"
        secondary="CONNECTING..."
      />
      <ScenePlant :position="[1.15, 1.1, 0.0]" />
      <SceneCoffeeMug :position="[1.1, 1.1, 0.55]" />
    </TresGroup>

    <SceneSimpleChair :position="[-0.2, 0, 1.4]" />
  </TresGroup>
</template>
