<script setup lang="ts">
// "Jack 3D" — Brian's jack model (jax.obj) in polished chrome, slow-spinning,
// sized for the top bar. The same model ships in four poses: the static tilt
// is applied to the mesh and the stage spins the world Y axis around it.
// Canvas context (env map, spin) lives in JackStage; SSR falls back to the
// static Knucklebone mark.
import { TresCanvas } from '@tresjs/core'
import { useScenePalette } from '@/composables/useScenePalette'
import JackStage from '@/components/logo/JackStage.vue'
import JackObjModel from '@/components/logo/JackObjModel.vue'
import LogoKnucklebone from '@/components/logo/Knucklebone.vue'

// jax.obj's native spike axis runs along Z; these tilts re-seat it per pose.
const POSES = {
  upright: [Math.PI / 2, 0, 0] as [number, number, number],
  kickstand: [Math.PI / 2, 0, -0.45] as [number, number, number],
  tossed: [0.6, 0, 0.5] as [number, number, number],
  compass: [0, 0, 0] as [number, number, number],
}

withDefaults(defineProps<{
  /** Canvas edge in px (square). */
  size?: number
  /** Spin speed multiplier; 0 freezes the pose. */
  speed?: number
  pose?: keyof typeof POSES
}>(), { size: 24, speed: 1, pose: 'upright' })

const { isDark } = useScenePalette()
</script>

<template>
  <ClientOnly>
    <div class="shrink-0 overflow-hidden" :style="{ width: `${size}px`, height: `${size}px` }">
      <TresCanvas :alpha="true" :clear-alpha="0">
        <TresPerspectiveCamera :position="[2.4, 1.7, 2.6]" :fov="35" :look-at="[0, 0, 0]" />
        <!-- env map does most of the shading; lights just add sparkle -->
        <TresAmbientLight :intensity="0.25" />
        <TresDirectionalLight :position="[6, 8, 4]" :intensity="isDark ? 0.9 : 0.7" :color="'#ffffff'" />
        <TresDirectionalLight :position="[-5, 3, -4]" :intensity="0.35" :color="isDark ? '#818cf8' : '#ffe9c4'" />
        <JackStage :speed="speed">
          <JackObjModel :rotation="POSES[pose]" />
        </JackStage>
      </TresCanvas>
    </div>
    <template #fallback>
      <LogoKnucklebone
        class="shrink-0 text-primary"
        :style="{ width: `${size}px`, height: `${size}px` }"
      />
    </template>
  </ClientOnly>
</template>
