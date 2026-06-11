<script setup lang="ts">
// Stage for the 3D jack variants: builds the PMREM RoomEnvironment (chrome
// needs something to reflect) and slow-tumbles whatever model is slotted in.
// Must live inside a TresCanvas (needs the renderer context).
import * as THREE from 'three'
import { useTresContext } from '@tresjs/core'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { onBeforeUnmount, onMounted, shallowRef } from 'vue'

const props = withDefaults(defineProps<{
  /** Tumble speed multiplier; 0 freezes the pose. */
  speed?: number
}>(), { speed: 1 })

const groupRef = shallowRef<THREE.Group | null>(null)
const { scene, renderer } = useTresContext()

let envTex: THREE.Texture | null = null
function buildEnv(r: THREE.WebGLRenderer) {
  const pmrem = new THREE.PMREMGenerator(r)
  envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
  scene.value.environment = envTex
  pmrem.dispose()
}

let animFrame = 0
onMounted(() => {
  const inst = renderer.instance as THREE.WebGLRenderer | undefined
  if (inst) buildEnv(inst)
  else renderer.onReady((r) => buildEnv(r as THREE.WebGLRenderer))

  let last = performance.now()
  let t = 0.9 // start mid-spin so the first frame already looks dimensional
  const tick = (now: number) => {
    const dt = Math.min((now - last) / 1000, 0.05)
    last = now
    t += dt * props.speed
    const g = groupRef.value
    if (g) g.rotation.y = t * 0.6 // nice slow spin, ~10s per turn
    animFrame = requestAnimationFrame(tick)
  }
  animFrame = requestAnimationFrame(tick)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(animFrame)
  if (scene.value.environment === envTex) scene.value.environment = null
  envTex?.dispose()
  envTex = null
})
</script>

<template>
  <TresGroup ref="groupRef">
    <slot />
  </TresGroup>
</template>
