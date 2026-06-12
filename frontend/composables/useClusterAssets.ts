// Generated assets for the Living Cluster scene (PRD 07 V2).
//
// The scene's machine chassis can be real meshes generated through the
// platform's own modalities (FLUX image → TRELLIS GLB) instead of procedural
// boxes. /design/cluster/assets.json maps each form factor to a GLB URL plus
// the attribution of the generation request that made it — the platform
// credits its own work. Loading is progressive enhancement: anything missing
// (no entry, fetch failure, parse failure) silently keeps the procedural
// fallback, so the scene always renders fully.

import { shallowRef, type ShallowRef } from 'vue'
import type { Object3D } from 'three'
import { Box3, Group, Vector3 } from 'three'
import type { HostFormFactor } from '@/composables/useClusterState'

export interface ClusterAssetEntry {
  url: string
  label?: string
  // Attribution — the generation request this asset came from.
  request_id?: string
  model?: string
  provider?: string
  seed?: number
  // Optional link target for the credit line (e.g. a shared request URL).
  href?: string
}

export interface LoadedClusterAsset {
  entry: ClusterAssetEntry
  // Normalized: centered on x/z, resting on y=0, max dimension = 1.
  object: Object3D
}

export type ClusterAssetMap = Map<HostFormFactor, LoadedClusterAsset>

// Module-level cache: the GLBs are shared by every scene on the page and
// across navigations within the SPA session.
let loadPromise: Promise<ClusterAssetMap> | null = null

async function loadAssets(): Promise<ClusterAssetMap> {
  const out: ClusterAssetMap = new Map()
  let manifest: { assets?: Record<string, ClusterAssetEntry | null> }
  try {
    const res = await fetch('/design/cluster/assets.json')
    if (!res.ok) return out
    manifest = await res.json()
  } catch {
    return out
  }
  const entries = Object.entries(manifest.assets ?? {}).filter(
    (pair): pair is [string, ClusterAssetEntry] => !!pair[1]?.url,
  )
  if (!entries.length) return out

  const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
  const loader = new GLTFLoader()
  await Promise.all(
    entries.map(
      ([key, entry]) =>
        new Promise<void>((resolve) => {
          loader.load(
            entry.url,
            (gltf) => {
              // Same normalization as ModelViewer: center, ground, unit-size,
              // so HostMachine only scales to its form factor's dims.
              const scene = gltf.scene
              const box = new Box3().setFromObject(scene)
              const size = box.getSize(new Vector3())
              const center = box.getCenter(new Vector3())
              const maxDim = Math.max(size.x, size.y, size.z) || 1
              const inner = new Group()
              inner.position.set(-center.x, -box.min.y, -center.z)
              inner.add(scene)
              const outer = new Group()
              outer.scale.setScalar(1 / maxDim)
              outer.add(inner)
              out.set(key as HostFormFactor, { entry, object: outer })
              resolve()
            },
            undefined,
            () => resolve(), // failed load → procedural fallback
          )
        }),
    ),
  )
  return out
}

export const useClusterAssets = (): ShallowRef<ClusterAssetMap> => {
  const assets = shallowRef<ClusterAssetMap>(new Map())
  if (import.meta.client) {
    loadPromise ??= loadAssets()
    void loadPromise.then((map) => {
      assets.value = map
    })
  }
  return assets
}
