<script setup lang="ts">
// Reusable studio-lit GLB viewer. Used identically on cards, the detail page
// and the public share page (see InferenceRequestCard / requests/[id] / s/[token]).
//
//  - Renders a GLB with neutral studio lighting + an environment map (PBR
//    reflections) and a soft contact shadow so the model reads as a real
//    object on a surface.
//  - `posterSrc` (the original input image) shows as the SSR/loading poster and
//    can be toggled back in as a corner inset — "the image that became this".
//  - `lazy` defers the WebGL canvas until the viewer scrolls into view, so a
//    feed of many models doesn't spin up a dozen contexts at once.
import { TresCanvas } from '@tresjs/core'
import { ContactShadows, Environment, OrbitControls } from '@tresjs/cientos'
import { ACESFilmicToneMapping, Box3, Group, SRGBColorSpace, Vector3, type Object3D } from 'three'
import { Box, Download, ImageOff, Images, Loader2, Rotate3d } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useImageLightbox } from '@/composables/useImageLightbox'

const props = withDefaults(
  defineProps<{
    src: string
    posterSrc?: string | null
    alt?: string
    autoRotate?: boolean
    // Defer mounting the WebGL canvas until the viewer is near the viewport.
    lazy?: boolean
    // Show the download-GLB control.
    downloadable?: boolean
    // Filename used when downloading the GLB.
    downloadName?: string
  }>(),
  { autoRotate: true, lazy: false, downloadable: true, downloadName: 'model.glb' },
)

const { isDark } = useTheme()
const lightbox = useImageLightbox()
const { downloading, download } = useFileDownload()

// Transparent canvas (clearAlpha 0) over a CSS backdrop, so the studio
// gradient follows the light/dark theme without re-rendering the scene.
const clearColor = computed(() => (isDark.value ? '#0a0d18' : '#f5f3ec'))

const container = ref<HTMLElement | null>(null)
const active = ref(false) // canvas mounts client-side once on screen
const loaded = ref(false)
const loadError = ref(false)
const showImage = ref(false)
let observer: IntersectionObserver | null = null

// The framed model, loaded imperatively (no <Suspense>/async child, which
// don't reliably mount/signal inside Tres's custom renderer). Rendered via
// <primitive>. shallowRef: it's a three Object3D, not reactive data.
const modelGroup = shallowRef<Group | null>(null)
let loadStarted = false

const disposeModel = () => {
  const g = modelGroup.value
  modelGroup.value = null
  if (!g) return
  g.traverse((o: Object3D) => {
    const mesh = o as unknown as { geometry?: { dispose?: () => void }; material?: unknown }
    mesh.geometry?.dispose?.()
    const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
    for (const m of mats as Array<Record<string, unknown> & { dispose?: () => void }>) {
      for (const k in m) {
        const v = m[k] as { isTexture?: boolean; dispose?: () => void } | null
        if (v && v.isTexture) v.dispose?.()
      }
      m.dispose?.()
    }
  })
}

// Load + frame the GLB: recentre on the floor (bottom at y=0, centred in x/z)
// and normalise scale so any model fills the same viewport box. Drives the
// loaded/error flags directly off the loader callbacks — rock solid.
const loadModel = async () => {
  if (loadStarted || !props.src) return
  loadStarted = true
  try {
    const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
    new GLTFLoader().load(
      props.src,
      (gltf) => {
        const scene = gltf.scene
        scene.traverse((o: Object3D) => {
          const mesh = o as unknown as { isMesh?: boolean; castShadow?: boolean; receiveShadow?: boolean }
          if (mesh.isMesh) {
            mesh.castShadow = true
            mesh.receiveShadow = true
          }
        })
        const box = new Box3().setFromObject(scene)
        const size = box.getSize(new Vector3())
        const center = box.getCenter(new Vector3())
        const maxDim = Math.max(size.x, size.y, size.z) || 1
        const inner = new Group()
        inner.position.set(-center.x, -box.min.y, -center.z)
        inner.add(scene)
        const outer = new Group()
        outer.scale.setScalar(2 / maxDim)
        outer.add(inner)
        modelGroup.value = outer
        loaded.value = true
      },
      undefined,
      () => { loadError.value = true },
    )
  } catch {
    loadError.value = true
  }
}

// Auto-rotate, paused while the user is dragging and resumed a beat later.
const rotating = ref(props.autoRotate)
let resumeTimer: ReturnType<typeof setTimeout> | null = null
const pauseRotate = () => {
  if (!props.autoRotate) return
  rotating.value = false
  if (resumeTimer) clearTimeout(resumeTimer)
}
const resumeRotate = () => {
  if (!props.autoRotate) return
  if (resumeTimer) clearTimeout(resumeTimer)
  resumeTimer = setTimeout(() => (rotating.value = true), 2500)
}

const activate = () => {
  active.value = true
  loadModel()
}

onMounted(() => {
  // Eager (detail/share): mount + load now. Lazy (feed cards): wait until the
  // viewer is near the viewport so a grid doesn't spin up many WebGL contexts
  // and download many large GLBs at once.
  if (!props.lazy || !container.value) {
    activate()
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        observer?.disconnect()
        activate()
      }
    },
    { rootMargin: '300px' },
  )
  observer.observe(container.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  if (resumeTimer) clearTimeout(resumeTimer)
  disposeModel()
})

const showPoster = computed(() => !!props.posterSrc && (!loaded.value || loadError.value))
const showSpinner = computed(() => active.value && !loaded.value && !loadError.value)
const openImage = () => props.posterSrc && lightbox.open(props.posterSrc)
</script>

<template>
  <div
    ref="container"
    class="model-viewer group/mv relative w-full overflow-hidden rounded-xl border"
    :class="isDark
      ? 'bg-[radial-gradient(120%_120%_at_50%_18%,#222a44_0%,#11151f_60%,#080a12_100%)]'
      : 'bg-[radial-gradient(120%_120%_at_50%_18%,#ffffff_0%,#eceae2_55%,#dcd8cd_100%)]'"
    @pointerdown="pauseRotate"
    @pointerup="resumeRotate"
    @pointerleave="resumeRotate"
  >
    <ClientOnly>
      <TresCanvas
        v-if="active && !loadError"
        :clear-color="clearColor"
        :clear-alpha="0"
        :alpha="true"
        :shadows="true"
        :tone-mapping="ACESFilmicToneMapping"
        :output-color-space="SRGBColorSpace"
        :dpr="[1, 2]"
        class="!absolute inset-0"
      >
        <TresPerspectiveCamera :position="[2.6, 1.9, 3.0]" :fov="35" />
        <OrbitControls
          :target="[0, 0.65, 0]"
          :enable-pan="false"
          :enable-damping="true"
          :auto-rotate="rotating"
          :auto-rotate-speed="0.8"
          :min-distance="1.6"
          :max-distance="9"
          :min-polar-angle="0.2"
          :max-polar-angle="1.5"
        />

        <!-- Studio rig: soft ambient fill, a strong key, a cool rim. -->
        <TresAmbientLight :intensity="0.45" />
        <TresDirectionalLight :position="[4, 7, 5]" :intensity="2.6" cast-shadow />
        <TresDirectionalLight :position="[-5, 3, -4]" :intensity="0.7" color="#bcd2ff" />
        <TresDirectionalLight :position="[0, 2, -6]" :intensity="0.5" />

        <primitive v-if="modelGroup" :object="modelGroup" />

        <ContactShadows
          :opacity="0.6"
          :scale="7"
          :blur="2.6"
          :far="3.2"
          :resolution="512"
          :position="[0, 0.002, 0]"
          color="#000000"
        />
        <!-- Lighting only (background stays the CSS gradient). -->
        <Environment preset="studio" />
      </TresCanvas>
    </ClientOnly>

    <!-- Poster / SSR / loading fallback (the original input image). -->
    <img
      v-if="showPoster"
      :src="posterSrc || undefined"
      :alt="alt || 'Source image'"
      class="pointer-events-none absolute inset-0 h-full w-full object-contain p-8"
      :class="showSpinner ? 'opacity-60' : 'opacity-100'"
    />
    <div
      v-else-if="!posterSrc && !active"
      class="absolute inset-0 flex items-center justify-center text-muted-foreground"
    >
      <Box class="size-8 opacity-40" />
    </div>

    <!-- Loading spinner while the GLB streams in. -->
    <div
      v-if="showSpinner"
      class="pointer-events-none absolute inset-0 flex items-center justify-center"
    >
      <Loader2 class="size-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Decode/network failure. -->
    <div
      v-if="loadError"
      class="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-md bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur"
    >
      <ImageOff class="size-3.5" /> Couldn't load 3D model
    </div>

    <!-- 3D badge (so a still poster still reads as interactive). -->
    <div
      class="pointer-events-none absolute left-2 top-2 inline-flex items-center gap-1 rounded-md bg-background/70 px-2 py-0.5 text-[11px] font-medium text-foreground/80 backdrop-blur"
    >
      <Rotate3d class="size-3.5" /> 3D
    </div>

    <!-- Original-image toggle + its corner inset. -->
    <template v-if="posterSrc">
      <button
        type="button"
        class="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md bg-background/70 text-foreground/80 backdrop-blur transition-colors hover:bg-background hover:text-foreground"
        :class="showImage ? 'ring-1 ring-primary' : ''"
        :title="showImage ? 'Hide original image' : 'Show original image'"
        :aria-pressed="showImage"
        @click.stop="showImage = !showImage"
      >
        <Images class="size-4" />
      </button>
      <button
        v-if="showImage"
        type="button"
        class="absolute right-2 top-12 w-1/3 max-w-[9rem] overflow-hidden rounded-lg border bg-background/80 shadow-lg backdrop-blur transition-transform hover:scale-[1.03]"
        title="Open original image"
        @click.stop="openImage"
      >
        <span class="block bg-muted/40 px-1.5 py-0.5 text-left text-[10px] uppercase tracking-wide text-muted-foreground">
          Source
        </span>
        <img :src="posterSrc" :alt="alt || 'Source image'" class="aspect-square w-full object-cover" />
      </button>
    </template>

    <!-- Download GLB. -->
    <button
      v-if="downloadable"
      type="button"
      class="absolute bottom-2 right-2 inline-flex size-8 items-center justify-center rounded-md bg-background/70 text-foreground/80 opacity-80 backdrop-blur transition-all hover:bg-background hover:text-foreground hover:opacity-100 disabled:opacity-50"
      :title="downloading ? 'Downloading…' : 'Download GLB'"
      :disabled="downloading"
      @click.stop="download(src, downloadName)"
    >
      <component :is="downloading ? Loader2 : Download" class="size-4" :class="downloading ? 'animate-spin' : ''" />
    </button>
  </div>
</template>

<style scoped>
.model-viewer {
  aspect-ratio: 4 / 3;
}
.model-viewer :deep(canvas) {
  touch-action: none;
}
</style>
