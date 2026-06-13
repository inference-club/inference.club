// Cluster-scene palette (PRD 07 design pass 2) — separate from the shared
// useScenePalette so re-skinning the Living Cluster doesn't repaint
// NetworkScene. Dark mode is a graphite stage lit by neon; light mode is a
// cool studio gray, not the warm beige of the network scene.
import { computed, type ComputedRef } from 'vue'
import { useTheme } from '@/composables/useTheme'

export interface ClusterPalette {
  deck: string
  deckBevel: string
  grid: string
  pedestal: string
  tower: string
  box: string
  slab: string
  satellite: string
  cable: string
  groundShadow: string
  text3d: string
  vent: string
}

const DARK: ClusterPalette = {
  deck: '#15171e',
  deckBevel: '#0b0d12',
  grid: '#1d7a9e',
  pedestal: '#0e1015',
  tower: '#262b36',
  box: '#1c212b',
  slab: '#b8923c',
  satellite: '#525c70',
  cable: '#22d3ee',
  groundShadow: '#000000',
  text3d: '#0c4a5e',
  vent: '#0a0d14',
}

const LIGHT: ClusterPalette = {
  deck: '#e3e5ea',
  deckBevel: '#c9ccd4',
  grid: '#b9bdc7',
  pedestal: '#d2d5db',
  tower: '#343a45',
  box: '#454c58',
  slab: '#c9a23c',
  satellite: '#c2c8d2',
  cable: '#0891b2',
  groundShadow: '#3a3d44',
  text3d: '#9aa0ab',
  vent: '#1a1e26',
}

const { isDark } = useTheme()
const palette: ComputedRef<ClusterPalette> = computed(() => (isDark.value ? DARK : LIGHT))

export function useClusterPalette() {
  return { palette, isDark }
}
