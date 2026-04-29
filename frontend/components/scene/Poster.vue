<script setup lang="ts">
import * as THREE from 'three'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'

const props = withDefaults(defineProps<{
  position: [number, number, number]
  rotation?: [number, number, number]
  size?: [number, number]            // frame width × height
  variant?: 'gradient' | 'stripes' | 'split' | 'sun'
  color1?: string
  color2?: string
  color3?: string
}>(), {
  rotation: () => [0, 0, 0],
  size: () => [0.9, 1.2],
  variant: 'gradient',
  color1: '#7c3aed',
  color2: '#22d3ee',
  color3: '#f59e0b',
})

const { palette, isDark } = useScenePalette()
const tex = shallowRef<THREE.CanvasTexture | null>(null)

function build() {
  tex.value?.dispose()
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 680
  const ctx = c.getContext('2d')!
  if (props.variant === 'gradient') {
    const g = ctx.createLinearGradient(0, 0, 0, c.height)
    g.addColorStop(0, props.color1)
    g.addColorStop(1, props.color2)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, c.width, c.height)
  } else if (props.variant === 'stripes') {
    const stripe = c.height / 6
    const colors = [props.color1, props.color2, props.color1, props.color3, props.color1, props.color2]
    for (let i = 0; i < colors.length; i++) {
      ctx.fillStyle = colors[i]!
      ctx.fillRect(0, i * stripe, c.width, stripe)
    }
  } else if (props.variant === 'split') {
    ctx.fillStyle = props.color1
    ctx.fillRect(0, 0, c.width, c.height)
    ctx.fillStyle = props.color2
    ctx.beginPath()
    ctx.moveTo(0, c.height)
    ctx.lineTo(c.width, c.height * 0.4)
    ctx.lineTo(c.width, c.height)
    ctx.closePath()
    ctx.fill()
  } else if (props.variant === 'sun') {
    // sky gradient + sun disc + horizon stripes
    const g = ctx.createLinearGradient(0, 0, 0, c.height * 0.7)
    g.addColorStop(0, props.color1)
    g.addColorStop(1, props.color2)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, c.width, c.height * 0.7)
    ctx.fillStyle = props.color3
    ctx.beginPath()
    ctx.arc(c.width / 2, c.height * 0.55, c.width * 0.28, 0, Math.PI * 2)
    ctx.fill()
    // horizon ground
    ctx.fillStyle = props.color1
    ctx.fillRect(0, c.height * 0.7, c.width, c.height * 0.3)
    // horizon stripes
    ctx.fillStyle = props.color2
    for (let i = 0; i < 5; i++) {
      const y = c.height * 0.72 + i * 0.05 * c.height
      ctx.fillRect(0, y, c.width, 6)
    }
  }
  const texture = new THREE.CanvasTexture(c)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  tex.value = texture
}

onMounted(() => { if (import.meta.client) build() })
watch(isDark, () => { if (import.meta.client) build() })
onBeforeUnmount(() => {
  tex.value?.dispose()
  tex.value = null
})
</script>

<template>
  <TresGroup :position="position" :rotation="rotation">
    <!-- Frame -->
    <TresMesh>
      <TresBoxGeometry :args="[size[0], size[1], 0.025]" />
      <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.5" />
    </TresMesh>
    <!-- Print -->
    <TresMesh :position="[0, 0, 0.014]">
      <TresPlaneGeometry :args="[size[0] - 0.08, size[1] - 0.08]" />
      <TresMeshBasicMaterial :map="tex" :color="tex ? '#ffffff' : color1" />
    </TresMesh>
  </TresGroup>
</template>
