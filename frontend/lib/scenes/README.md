# Scenes

Small, looping three.js pieces that explain the club without words. They live
on the homepage today and are built to be reused anywhere.

```
lib/scenes/
  theme.ts        the palette and the colour of each kind of signal and role
  stage.ts        the stage: renderer, sizing, pausing, reduced motion, helpers
  scenes/
    signals.ts    every kind of signal, as six lanes crossing a line
    assemble.ts   a real 3D model building itself out of its source picture
    exchange.ts   people and agents ask; members' machines answer
    network.ts    one lit window, then a street, then a town
components/scenes/
  SceneStage.vue  the Vue frame a scene plays in
public/scenes/models/
  *.pts, *.webp   real generated 3D models as point clouds, and their pictures
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
- **`@state`** receives whatever the scene reports with `ctx.emit(name, value)`:
  the network's running count, or which model `assemble` is showing.

`SceneStage` does not load three.js or the scene until the panel is within
500px of the viewport. Scenes stop drawing when off screen, cap the pixel
ratio at 2 (1.5 on phones) and draw a single still frame when the person has
asked for reduced motion.

| Scene | Options | Reports |
| --- | --- | --- |
| `signals` | `art`: picture URLs; `models`: `.pts` URLs (optional) | |
| `assemble` | `models`: `{ src, image }` per model; `seconds` each is shown | `model`: index on show |
| `exchange` | `callers`, `machines` (counts) | |
| `network` | `nodes` (count) | `count`: lights on |

## Writing a scene

A scene is one function. It gets a context, builds its objects, and returns
`update`:

```ts
import { sparks, type SceneFactory } from '../stage'

const fireflies: SceneFactory<{ count?: number }> = (ctx) => {
  const { THREE, palette, scene } = ctx
  const n = ctx.options?.count ?? 40
  const lights = sparks(ctx, n)                // n round lights, one draw call
  scene.add(lights.object)
  const amber = new THREE.Color(palette.amber)
  ctx.camera.position.set(0, 0, 8)

  return {
    poster: 2,                                 // the moment drawn for reduced motion
    update(t) {                                // t: seconds since the scene began
      for (let i = 0; i < n; i++) {
        lights.set(i, Math.sin(t + i) * 3, Math.cos(t * 0.7 + i * 2), 0, amber, 0.3, 0.8)
      }
      lights.commit()
    },
  }
}
export default fireflies
```

Rules that keep scenes cheap and consistent:

1. **Colour only from `ctx.palette`** (or `signalColor` / `roleColor`). Do not
   hard-code colours; the same scene must read at night and on paper. The
   exceptions are real things shown as themselves: generated pictures and the
   colours of a generated model.
2. **Everything with `dispose()` goes through `ctx.keep()`**: geometries,
   materials, textures.
3. **Loop, with no dead time.** Derive everything from `t`; do not accumulate
   state that drifts. Use `seeded()` at build time and `hash()` per frame
   instead of `Math.random()`, so the picture is the same on every visit.
   Something should be moving at every moment, including across the loop
   point.
4. **No text in the canvas.** Report numbers with `ctx.emit` and let the page
   draw them.
5. **Stay light**: instanced meshes and point clouds, no shadows, no
   post-processing, no per-frame allocation.
6. **Fit any shape.** Handle `resize({ aspect })`; phones are tall. For flat
   pictures use `flatCamera(ctx, height)`.
7. **Ease everything.** Nothing should start or stop abruptly: use `smooth`,
   `easeInOut`, `easeOut`, or `easeBack` for things that pop into place.

### Helpers in `stage.ts`

| Helper | For |
| --- | --- |
| `sparks(ctx, n, { hard })` | A cloud of round lights with per-light position, colour, size (world units) and opacity: glows, nodes, trails. A trail is the same path drawn again a little earlier, smaller and fainter. |
| `loadPoints(url, limit)` | Load a generated 3D model as points (`.pts`). Any prefix of the file is an even sample, so `limit` is a cheap level of detail. |
| `modelCloud(ctx, model, opts)` | A point model that can `build` itself from a loose cloud (or from a flat `sheet` elsewhere), `turn`, and `dissolve`. The work is done in the vertex shader. |
| `ctx.glow(color, opacity)` | A flat material that adds light at night and inks on paper. |
| `flatCamera(ctx, height)` | An orthographic camera showing `height` world units. |
| `seeded(seed)`, `hash(n)` | Repeatable random numbers. |
| `ramp`, `smooth`, `clamp01`, `easeOut`, `easeInOut`, `easeBack` | Timing. |
| `softDot`, `sampleImage` | A round light texture for sprites; average colours of a picture on a grid. |

Point sizes are limited by the graphics driver (often to about 64–500 pixels),
so keep `sparks` for lights up to a few world units across and use a mesh for
anything bigger.

## The theme

At night the ground is a deep blue-black and everything that matters is a
bright, saturated light; lights add up where they cross. In the light theme
the same drawing is made in strong inks on warm white paper, without adding.
The generated artwork on the homepage is deliberately in every style going,
so the scenes carry the page's colour on their own.

| Kind of signal | Colour role |
| --- | --- |
| text | sky |
| image | amber |
| speech | teal |
| music | violet (running into pink) |
| video | coral |
| 3D shape | pink |

| Role | Drawn as |
| --- | --- |
| a person | a round ink dot |
| an agent | a lime diamond |
| a member's machine | an amber square |
| something private | a dashed violet ring |

Keep those meanings if you add a scene. In `signals`, the bright vertical line
is the machine: raw material on its left, the finished thing on its right.

## Real 3D models

`public/scenes/models/` holds models made by the club's 3D service, sampled
to 16,000 coloured points each by `scripts/showcase/mesh_points.py`, with the
picture each was made from and an `index.json` of where it came from (model,
seed, GPU, seconds, triangle count). `signals` shows them in its 3D lane and
`assemble` builds them. If no model can be loaded, `signals` falls back to
plain wireframe solids and `assemble` fails quietly (the panel stays blank),
so the page should only mount `assemble` when `index.json` lists a model.

## Checking a scene

Headless Chromium needs software WebGL to draw these:
`chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] })`.
It draws slowly, so scene time runs slower than the clock. Look at phone and
desktop widths, both themes, and with reduced motion on.
