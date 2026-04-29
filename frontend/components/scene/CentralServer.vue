<script setup lang="ts">
defineProps<{
  position: [number, number, number]
}>()
</script>

<template>
  <TresGroup :position="position">
    <SceneFloorPad :size="[3.6, 3.0]" :bevel="true" />
    <SceneServerRack :position="[-0.45, 0, -0.1]" />
    <SceneLogoCube :position="[0.85, 0.55, 0.55]" />
  </TresGroup>
</template>
