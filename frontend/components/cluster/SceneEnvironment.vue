<script setup lang="ts">
// Renderer + scene setup for the Living Cluster (PRD 07 design pass 2).
// Must live inside the TresCanvas. Three jobs:
//   1. PMREM RoomEnvironment as scene.environment — metallic and glossy
//      materials (the chrome jack, gunmetal machines) need a world to
//      reflect; scene.environmentIntensity dims it per theme.
//   2. Soft shadow maps — grounding the machines on the deck.
//   3. ACES filmic tone mapping — keeps neon emissives from clipping.
import * as THREE from 'three'
import { useTresContext } from '@tresjs/core'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { onBeforeUnmount, onMounted, watchEffect } from 'vue'
import { useClusterPalette } from '@/composables/useClusterPalette'

const { scene, renderer } = useTresContext()
const { isDark } = useClusterPalette()

let envTex: THREE.Texture | null = null

function configure(r: THREE.WebGLRenderer) {
  r.shadowMap.enabled = true
  r.shadowMap.type = THREE.PCFSoftShadowMap
  r.toneMapping = THREE.ACESFilmicToneMapping
  const pmrem = new THREE.PMREMGenerator(r)
  envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
  scene.value.environment = envTex
  pmrem.dispose()
}

onMounted(() => {
  const inst = renderer.instance as THREE.WebGLRenderer | undefined
  if (inst) configure(inst)
  else renderer.onReady(r => configure(r as THREE.WebGLRenderer))
})

watchEffect(() => {
  scene.value.environmentIntensity = isDark.value ? 0.5 : 0.9
  const inst = renderer.instance as THREE.WebGLRenderer | undefined
  if (inst) inst.toneMappingExposure = isDark.value ? 1.05 : 1.0
})

onBeforeUnmount(() => {
  if (scene.value.environment === envTex) scene.value.environment = null
  envTex?.dispose()
  envTex = null
})
</script>

<template>
  <TresGroup />
</template>
