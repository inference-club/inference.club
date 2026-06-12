// Shared radial glow sprite texture for the 3D scenes' dark-mode neon look.
// A white radial gradient rendered once to a canvas; tint it via material
// color + additive blending and it reads as cheap, postprocessing-free bloom.
import { CanvasTexture } from 'three'

let cached: CanvasTexture | null = null

export function radialGlowTexture(): CanvasTexture | null {
  if (!import.meta.client) return null
  if (cached) return cached
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255,255,255,0.9)')
  g.addColorStop(0.35, 'rgba(255,255,255,0.4)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  cached = new CanvasTexture(canvas)
  return cached
}
