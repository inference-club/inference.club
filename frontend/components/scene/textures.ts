import * as THREE from 'three'

export function makeScreenTexture(opts: {
  primary: string
  secondary: string
  bg: string
  fg: string
  sub: string
}): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 320
  const ctx = c.getContext('2d')!
  ctx.fillStyle = opts.bg
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = opts.fg
  ctx.font = 'bold 92px Inter, system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(opts.primary, c.width / 2, c.height / 2 - 28)
  ctx.fillStyle = opts.sub
  ctx.font = 'bold 28px Inter, system-ui, sans-serif'
  ctx.fillText(opts.secondary, c.width / 2, c.height / 2 + 56)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

export function makeLogoTexture(bg: string, fg: string): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 256
  const ctx = c.getContext('2d')!
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = fg
  ctx.font = 'bold 38px Inter, system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('inference', c.width / 2, c.height / 2 - 18)
  ctx.fillText('.club', c.width / 2, c.height / 2 + 22)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}
