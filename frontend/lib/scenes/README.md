# Scenes

Small, looping three.js pieces that explain the club without words. They live
on the homepage today and are built to be reused anywhere.

```
lib/scenes/
  theme.ts        the palette ("porch lights") and the colour of each kind of signal
  stage.ts        the stage: renderer, sizing, pausing, reduced motion, helpers
  scenes/
    signals.ts    every kind of signal, as six lanes
    exchange.ts   people and agents ask; members' machines answer
    network.ts    one lit window, then a street, then a town
components/scenes/
  SceneStage.vue  the Vue frame a scene plays in
```

## Using a scene

```vue
<script setup lang="ts">
import SceneStage from '@/components/scenes/SceneStage.vue'
const load = () => import('@/lib/scenes/scenes/network')
</script>

<template>
  <SceneStage :load="load" label="Lights linking into a network" class="h-96 rounded-3xl border">
    <template #overlay>
      <p class="absolute left-4 top-4">Any HTML drawn over the canvas</p>
    </template>
  </SceneStage>
</template>
```

- **Size** comes from the class you give `SceneStage`; the scene fills it.
- **`label`** is read to people who cannot see the picture. Always write one.
- **`options`** are passed to the scene. Pass a constant or a `computed`: a new
  object rebuilds the scene.
- **`#overlay`** is for text. Keep words in HTML (sharp, selectable,
  translatable) and shapes in the scene.
- **`@state`** receives whatever the scene reports with `ctx.emit(name, value)`,
  for example the network's running count.

`SceneStage` does not load three.js or the scene until the panel is within
500px of the viewport. Scenes stop drawing when off screen, cap the pixel
ratio at 2 (1.5 on phones) and draw a single still frame when the person has
asked for reduced motion.

## Writing a scene

A scene is one function. It gets a context, builds its objects, and returns
`update`:

```ts
import type { SceneFactory } from '../stage'

const fireflies: SceneFactory<{ count?: number }> = (ctx) => {
  const { THREE, palette, scene } = ctx
  const light = new THREE.Mesh(
    ctx.keep(new THREE.SphereGeometry(0.2)),   // keep() frees it on unmount
    ctx.glow(palette.amber),                   // glows at night, inks on paper
  )
  scene.add(light)
  ctx.camera.position.set(0, 0, 8)

  return {
    poster: 2,                                 // the moment drawn for reduced motion
    update(t) {                                // t: seconds since the scene began
      light.position.x = Math.sin(t) * 3
    },
  }
}
export default fireflies
```

Rules that keep scenes cheap and consistent:

1. **Colour only from `ctx.palette`** (or `signalColor`). Do not hard-code
   colours; the same scene must read at night and on paper.
2. **Everything with `dispose()` goes through `ctx.keep()`**: geometries,
   materials, textures.
3. **Loop.** Derive everything from `t`; do not accumulate state that drifts.
   Use `seeded()` instead of `Math.random()` so the picture is the same on
   every visit.
4. **No text in the canvas.** Report numbers with `ctx.emit` and let the page
   draw them.
5. **Stay light**: instanced meshes and point clouds, no shadows, no
   post-processing, no per-frame allocation.
6. **Fit any shape.** Handle `resize({ aspect })`; phones are tall. For flat
   pictures use `flatCamera(ctx, height)`.

Helpers in `stage.ts`: `seeded`, `ramp`, `smooth`, `clamp01`, `softDot`
(a round light texture), `flatCamera`, `sampleImage` (average colours of a
picture on a grid).

## The theme

Night is deep indigo; the things that matter are small warm lights. In the
light theme the same drawing is indigo ink on cream paper. The generated
artwork on the homepage is made in the same palette and print style (see
`theme` in `scripts/showcase/showcase.json`), so pictures and scenes read as
one set.

| Kind of signal | Colour role |
| --- | --- |
| text | ink |
| image | amber |
| speech | teal |
| music | violet |
| video | coral |
| 3D shape | sky |

A machine is an amber square, a person a round ink dot, an agent a coral
diamond, something private a dashed violet ring. Keep those meanings if you
add a scene.

## Checking a scene

Headless Chromium needs software WebGL to draw these:
`chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] })`.
Look at phone and desktop widths, both themes, and with reduced motion on.
