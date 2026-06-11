<script setup lang="ts">
// Logo exploration — toy-jack marks proposed to replace the node-mesh logo.
// Each option has a stable identifier; picking one means swapping it into
// AppLogo.vue, public/logo.svg (favicon), the sidebar tile, and the OG image.
definePageMeta({ layout: 'app', middleware: 'staff' })

import LogoOnesies from '@/components/logo/Onesies.vue'
import LogoKnucklebone from '@/components/logo/Knucklebone.vue'
import LogoSixer from '@/components/logo/Sixer.vue'
import LogoPickup from '@/components/logo/Pickup.vue'
import LogoTradesies from '@/components/logo/Tradesies.vue'
import LogoChromies from '@/components/logo/Chromies.vue'
import LogoTumble from '@/components/logo/Tumble.vue'

const groups = [
  {
    title: 'Round 2 — from the reference photo',
    note: 'Real-toy geometry: 3/4 perspective, four ball arms (near bigger than far), two pointed spikes.',
    options: [
      {
        id: 'tradesies',
        name: 'Tradesies',
        mark: LogoTradesies,
        desc: 'The real toy in perspective, monoline: vertical spikes, near ball pair low/wide/big, far pair high/narrow/small — the way a photographed jack reads head-on. Most faithful to the actual metal toy while staying in the site’s stroke style.',
      },
      {
        id: 'chromies',
        name: 'Chromies',
        mark: LogoChromies,
        desc: 'The perspective jack as polished chrome — steel gradients, radial ball highlights, mirror spikes. Self-colored (ignores theme color), so it looks identical on any background and matches the 3D model exactly.',
      },
      {
        id: 'tumble',
        name: 'Tumble',
        mark: LogoTumble,
        desc: 'The perspective jack as a solid silhouette, tilted like it just landed from a toss. Dynamic and favicon-strong; the asymmetry makes it recognizable at a glance.',
      },
    ],
  },
  {
    title: 'Round 1',
    note: '',
    options: [
      {
        id: 'onesies',
        name: 'Onesies',
        mark: LogoOnesies,
        desc: 'The current node-mesh mark evolved into a jack — the four ball-tipped arms and hub stay exactly where they are, and the vertical spike axis makes it the toy. Most continuity with today’s brand; monoline, matches the lucide icon set used everywhere else.',
      },
      {
        id: 'knucklebone',
        name: 'Knucklebone',
        mark: LogoKnucklebone,
        desc: 'A solid-silhouette jack named after the ancient game. One filled shape with tapered spikes and chunky balls — the boldest at tiny sizes, so it’s the strongest favicon candidate.',
      },
      {
        id: 'sixer',
        name: 'Sixer',
        mark: LogoSixer,
        desc: 'A dimensional jack in isometric perspective: crossing arms fade with depth via opacity layers while the spike and center sphere sit in front. Suggests the 3D toy with a single color.',
      },
      {
        id: 'pickup',
        name: 'Pickup',
        mark: LogoPickup,
        desc: 'A jack caught mid-game with the bouncy ball in the air beside it. The most playful option, with an asymmetric silhouette that’s easy to recognize.',
      },
    ],
  },
]

const sizes = [16, 20, 24, 32, 48]

const jack3dVariants = [
  {
    id: 'jack-3d-cast',
    name: 'Cast',
    variant: 'cast' as const,
    desc: 'Slender die-cast proportions. Each arm is one continuous lathed surface — flared base, thin rod, smooth swell into the ball — so joints are fillets, and the spikes taper to a soft rounded tip.',
  },
  {
    id: 'jack-3d-chunky',
    name: 'Chunky',
    variant: 'chunky' as const,
    desc: 'Same smooth construction with fat toy proportions: thicker rods, bigger balls, shorter blunter spikes. The most readable at top-bar size.',
  },
  {
    id: 'jack-3d-molten',
    name: 'Molten',
    variant: 'molten' as const,
    desc: 'One metaball isosurface — hub, rods, balls, and spikes all melt into each other with no seams at all, like the jack was poured from liquid metal.',
  },
]
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 sm:px-6 py-6">
    <h1 class="text-2xl font-semibold tracking-tight">Logo exploration: the jack</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Toy-jack candidates for the site mark. Each option shows scale steps, the top-bar
      lockup, the sidebar tile, and favicon tiles. The animated chrome 3D jack at the bottom
      can pair with any static mark. To pick one, say
      <span class="font-medium text-foreground">&ldquo;implement &lt;name&gt;&rdquo;</span>.
    </p>

    <template v-for="group in groups" :key="group.title">
      <div class="mt-12 border-b pb-2">
        <h2 class="text-base font-semibold uppercase tracking-wide">{{ group.title }}</h2>
        <p v-if="group.note" class="mt-0.5 text-sm text-muted-foreground">{{ group.note }}</p>
      </div>

      <section v-for="opt in group.options" :key="opt.id" class="mt-8">
        <div class="flex items-baseline gap-2">
          <h3 class="text-lg font-semibold">{{ opt.name }}</h3>
          <code class="text-xs text-muted-foreground">{{ opt.id }}</code>
        </div>
        <p class="mt-1 text-sm text-muted-foreground">{{ opt.desc }}</p>

        <!-- scale steps -->
        <div class="mt-4 flex items-end gap-5 rounded-lg border p-4">
          <div v-for="s in sizes" :key="s" class="flex flex-col items-center gap-1.5">
            <component :is="opt.mark" class="text-foreground" :style="{ width: `${s}px`, height: `${s}px` }" />
            <span class="text-[10px] text-muted-foreground">{{ s }}</span>
          </div>
          <div class="flex flex-col items-center gap-1.5">
            <component :is="opt.mark" class="text-primary" style="width: 48px; height: 48px" />
            <span class="text-[10px] text-muted-foreground">primary</span>
          </div>
        </div>

        <!-- top bar lockup -->
        <div class="mt-3 flex h-12 items-center gap-2 rounded-lg border px-4">
          <component :is="opt.mark" class="size-6 shrink-0 text-primary" />
          <span class="whitespace-nowrap font-bold text-xl">inference.club</span>
        </div>

        <!-- sidebar tile + favicon tiles -->
        <div class="mt-3 flex flex-wrap items-center gap-4 rounded-lg border p-4">
          <div class="flex items-center gap-2">
            <div class="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <component :is="opt.mark" class="size-4" />
            </div>
            <span class="text-xs text-muted-foreground">sidebar</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex size-8 items-center justify-center rounded-md" style="background: #4f46e5">
              <component :is="opt.mark" class="size-6 text-white" />
            </div>
            <div class="flex size-4 items-center justify-center rounded-sm" style="background: #4f46e5">
              <component :is="opt.mark" class="size-3.5 text-white" />
            </div>
            <span class="text-xs text-muted-foreground">favicon 32 / 16</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex size-8 items-center justify-center rounded-md border bg-white">
              <component :is="opt.mark" class="size-6" style="color: #4f46e5" />
            </div>
            <div class="flex size-8 items-center justify-center rounded-md" style="background: #0a0a16">
              <component :is="opt.mark" class="size-6" style="color: #a5b4fc" />
            </div>
            <span class="text-xs text-muted-foreground">light / dark tile</span>
          </div>
        </div>
      </section>
    </template>

    <!-- animated 3D jacks -->
    <div class="mt-12 border-b pb-2">
      <h2 class="text-base font-semibold uppercase tracking-wide">Jack 3D — three builds</h2>
      <p class="mt-0.5 text-sm text-muted-foreground">
        Animated chrome jacks (full metalness + studio reflections), all with filleted
        ball-to-rod joints and dull rounded points. Any build can pair with any static mark.
      </p>
    </div>

    <section v-for="v in jack3dVariants" :key="v.id" class="mt-8">
      <div class="flex items-baseline gap-2">
        <h3 class="text-lg font-semibold">{{ v.name }}</h3>
        <code class="text-xs text-muted-foreground">{{ v.id }}</code>
      </div>
      <p class="mt-1 text-sm text-muted-foreground">{{ v.desc }}</p>

      <div class="mt-4 flex h-12 items-center gap-2 rounded-lg border px-4">
        <LogoJack3D :size="26" :variant="v.variant" />
        <span class="whitespace-nowrap font-bold text-xl">inference.club</span>
      </div>

      <div class="mt-3 flex items-center justify-center rounded-lg border p-6">
        <LogoJack3D :size="150" :speed="0.8" :variant="v.variant" />
      </div>
    </section>
  </div>
</template>
