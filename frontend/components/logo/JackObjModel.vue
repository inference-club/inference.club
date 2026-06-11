<script setup lang="ts">
// Brian's jack model (public/design/jax.obj) with the chrome finish. The OBJ
// is a 43k-triangle soup, so on first load we weld vertices, recompute smooth
// normals, center, and normalize scale — then cache the geometry at module
// level so every canvas instance on the page shares one parse.
import * as THREE from 'three'
import { onMounted, shallowRef } from 'vue'
import { useChromeMaterials } from '@/components/logo/chrome'

const props = withDefaults(defineProps<{
  /** Static pose tilt; the stage spins the world Y axis around it. */
  rotation?: [number, number, number]
}>(), { rotation: () => [0, 0, 0] })

const { ballMat } = useChromeMaterials()

let geoPromise: Promise<THREE.BufferGeometry> | null = null
function loadJackGeometry(): Promise<THREE.BufferGeometry> {
  geoPromise ||= (async () => {
    const { OBJLoader } = await import('three/examples/jsm/loaders/OBJLoader.js')
    const { mergeGeometries, mergeVertices } = await import('three/examples/jsm/utils/BufferGeometryUtils.js')
    const obj = await new OBJLoader().loadAsync('/design/jax.obj')
    const geos: THREE.BufferGeometry[] = []
    obj.traverse((c) => {
      if ((c as THREE.Mesh).isMesh) geos.push((c as THREE.Mesh).geometry as THREE.BufferGeometry)
    })
    let geo = geos.length > 1 ? mergeGeometries(geos) : geos[0]
    // drop exporter normals/uvs so identical positions weld, then re-smooth
    geo.deleteAttribute('normal')
    geo.deleteAttribute('uv')
    geo = mergeVertices(geo)
    geo.computeVertexNormals()
    geo.center()
    geo.computeBoundingSphere()
    const s = 1.05 / (geo.boundingSphere?.radius ?? 1)
    geo.scale(s, s, s)
    return geo
  })()
  return geoPromise
}

const geometry = shallowRef<THREE.BufferGeometry | null>(null)
onMounted(async () => {
  geometry.value = await loadJackGeometry()
})
// Shared module-level geometry: deliberately not disposed on unmount.
</script>

<template>
  <TresMesh v-if="geometry" :geometry="geometry" :rotation="props.rotation">
    <TresMeshStandardMaterial v-bind="ballMat" />
  </TresMesh>
</template>
