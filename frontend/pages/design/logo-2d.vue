<script setup lang="ts">
// 2D logo review board — flat "projected shadow" silhouettes of the 3D jack
// (rendered offline from public/design/jax.obj into public/logo2d/*.png; see
// .captures/gen-shadows.mjs). The client picks a shape, a fill (solid or
// gradient), and a backdrop, and previews how each reads down to favicon size.
definePageMeta({ layout: 'app', middleware: 'staff' })

interface Option { slug: string; name: string; caption: string }
// Ordered best-first. Slug = the generated PNG in /logo2d/.
const OPTIONS: Option[] = [
  { slug: 'facey', name: 'Northstar', caption: 'Face-on — clean 4-point star' },
  { slug: 'iso', name: 'Asterisk', caption: 'Isometric — classic 6-point jack' },
  { slug: 'facex', name: 'Crosscut', caption: 'Side-on — knobbed plus' },
  { slug: 'plumb', name: 'Plumb', caption: 'Top-down the spike' },
  { slug: 'corner', name: 'Jackstone', caption: 'Near-corner — a knob up front' },
  { slug: 'lean', name: 'Lean', caption: 'Tilted three-quarter' },
  { slug: 'isolow', name: 'Drift', caption: 'Low isometric' },
  { slug: 'oblique', name: 'Toss', caption: 'Oblique tumble' },
  { slug: 'isoflat', name: 'Skew', caption: 'Flattened iso' },
]

interface Swatch { name: string; value: string }
const FILLS: Swatch[] = [
  { name: 'Ink', value: '#0b0f19' },
  { name: 'Slate', value: '#475569' },
  { name: 'Indigo', value: '#6366f1' },
  { name: 'White', value: '#ffffff' },
  { name: 'Indigo→Violet', value: 'linear-gradient(135deg,#6366f1,#a855f7)' },
  { name: 'Sky→Cyan', value: 'linear-gradient(135deg,#0ea5e9,#06b6d4)' },
  { name: 'Sunset', value: 'linear-gradient(135deg,#f59e0b,#ef4444)' },
  { name: 'Chrome', value: 'linear-gradient(160deg,#e5e7eb,#9ca3af 42%,#f8fafc 58%,#64748b)' },
]
const BACKDROPS: Swatch[] = [
  { name: 'White', value: '#ffffff' },
  { name: 'Paper', value: '#f3f4f6' },
  { name: 'Ink', value: '#0b0f19' },
  { name: 'Indigo night', value: '#1e1b4b' },
  { name: 'Dawn', value: 'linear-gradient(135deg,#fdf2f8,#ede9fe 50%,#e0f2fe)' },
  { name: 'Dusk', value: 'linear-gradient(135deg,#312e81,#1e1b4b 55%,#0b0f19)' },
  { name: 'Mesh', value: 'radial-gradient(circle at 28% 22%,#6366f1,transparent 42%),radial-gradient(circle at 82% 72%,#06b6d4,transparent 45%),#0b0f19' },
]

const fill = ref(FILLS[0].value)
const backdrop = ref(BACKDROPS[0].value)
const soft = ref(false) // render as a soft cast shadow instead of a flat fill

const shapeStyle = (slug: string, px: number) => ({
  width: `${px}px`,
  height: `${px}px`,
  background: fill.value,
  WebkitMaskImage: `url(/logo2d/${slug}.png)`,
  maskImage: `url(/logo2d/${slug}.png)`,
  WebkitMaskSize: 'contain',
  maskSize: 'contain',
  WebkitMaskRepeat: 'no-repeat',
  maskRepeat: 'no-repeat',
  WebkitMaskPosition: 'center',
  maskPosition: 'center',
  ...(soft.value ? { filter: 'blur(1.5px)', opacity: '0.55' } : {}),
})

const FAVICON_SIZES = [32, 24, 16]
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <h1 class="text-2xl font-semibold tracking-tight">2D logo — projected shadows</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Flat silhouettes cast from the 3D jack, one per projection angle. Pick a fill and a
      backdrop, then tell me which shape (by name) to ship — I'll cut the favicon from it.
    </p>

    <!-- Controls -->
    <div class="mt-6 space-y-4 rounded-xl border p-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Shape fill</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="s in FILLS"
            :key="s.name"
            class="size-8 rounded-full border shadow-sm transition-transform hover:scale-110"
            :class="fill === s.value ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''"
            :style="{ background: s.value }"
            :title="s.name"
            @click="fill = s.value"
          />
        </div>
      </div>
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Backdrop</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="s in BACKDROPS"
            :key="s.name"
            class="size-8 rounded-md border shadow-sm transition-transform hover:scale-110"
            :class="backdrop === s.value ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''"
            :style="{ background: s.value }"
            :title="s.name"
            @click="backdrop = s.value"
          />
        </div>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <Switch id="soft" v-model="soft" />
        <span>Soft cast shadow <span class="text-muted-foreground">(blur + fade, like a real shadow)</span></span>
      </label>
    </div>

    <!-- Options grid -->
    <div class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="o in OPTIONS" :key="o.slug" class="rounded-xl border overflow-hidden">
        <!-- Big preview on the chosen backdrop -->
        <div
          class="flex aspect-[4/3] items-center justify-center"
          :style="{ background: backdrop }"
        >
          <div :style="shapeStyle(o.slug, 150)" />
        </div>
        <!-- Caption + favicon-size strip -->
        <div class="flex items-center justify-between gap-3 border-t px-3 py-2">
          <div class="min-w-0">
            <p class="font-medium leading-tight">{{ o.name }}</p>
            <p class="text-[11px] text-muted-foreground truncate">{{ o.caption }}</p>
          </div>
          <div class="flex items-end gap-1.5 shrink-0" title="Favicon sizes">
            <div
              v-for="px in FAVICON_SIZES"
              :key="px"
              class="flex items-center justify-center rounded border"
              :style="{ width: `${px + 8}px`, height: `${px + 8}px`, background: backdrop }"
            >
              <div :style="shapeStyle(o.slug, px)" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
