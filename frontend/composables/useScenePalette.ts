import { computed, type ComputedRef } from 'vue'
import { useTheme } from '@/composables/useTheme'

export interface ScenePalette {
  floor: string
  floorBevel: string
  wall: string
  roomAccent: string
  desk: string
  deskDark: string
  fabric: string
  fabricDark: string
  blanket: string
  pillow: string
  pc: string
  pcAccent: string
  screenBezel: string
  windowGlass: string
  pictureFrame: string
  pictureArt: string
  plantPot: string
  plantLeaves: string
  plantLeavesAlt: string
  mug: string
  mugInside: string
  laptopBody: string
  serverBody: string
  serverSlot: string
  serverAccent: string
  logoWhite: string
  logoText: string
  pillFill: string
  pillBorder: string
  linkTailscale: string
  linkApi: string
  pulseTail: string
  pulseApi: string
  ground: string
}

const DARK: ScenePalette = {
  floor: '#1c2238',
  floorBevel: '#161b2c',
  wall: '#232a45',
  roomAccent: '#2a324d',
  desk: '#5a4530',
  deskDark: '#3b2c1e',
  fabric: '#4a5468',
  fabricDark: '#2c3344',
  blanket: '#3a4054',
  pillow: '#cbd2e6',
  pc: '#0d1018',
  pcAccent: '#22d3ee',
  screenBezel: '#05060c',
  windowGlass: '#1e3a5f',
  pictureFrame: '#2a324d',
  pictureArt: '#4f6286',
  plantPot: '#3b2c1e',
  plantLeaves: '#4ea372',
  plantLeavesAlt: '#6ec79a',
  mug: '#2a3045',
  mugInside: '#1a1d2a',
  laptopBody: '#5a6478',
  serverBody: '#0d1018',
  serverSlot: '#181d28',
  serverAccent: '#22d3ee',
  logoWhite: '#f0f0fa',
  logoText: '#a5b4fc',
  pillFill: '#0f1525',
  pillBorder: '#3949a8',
  linkTailscale: '#22d3ee',
  linkApi: '#a855f7',
  pulseTail: '#67e8f9',
  pulseApi: '#c084fc',
  ground: '#0a0d18',
}

const LIGHT: ScenePalette = {
  floor: '#e9e6df',
  floorBevel: '#cfcabf',
  wall: '#dcd8cf',
  roomAccent: '#cfcabf',
  desk: '#c9a079',
  deskDark: '#a07a55',
  fabric: '#94a3b8',
  fabricDark: '#475569',
  blanket: '#5b6677',
  pillow: '#e2e8f0',
  pc: '#1f2937',
  pcAccent: '#22d3ee',
  screenBezel: '#0b0b14',
  windowGlass: '#cfe7f1',
  pictureFrame: '#ffffff',
  pictureArt: '#94a3b8',
  plantPot: '#d4d0c5',
  plantLeaves: '#3f8f5f',
  plantLeavesAlt: '#4ea372',
  mug: '#ffffff',
  mugInside: '#3a2a1c',
  laptopBody: '#cbd0d6',
  serverBody: '#1f2329',
  serverSlot: '#3b424d',
  serverAccent: '#0ea5e9',
  logoWhite: '#fdfdfb',
  logoText: '#6366f1',
  pillFill: '#f6f4ee',
  pillBorder: '#cdc7b8',
  linkTailscale: '#06b6d4',
  linkApi: '#7c3aed',
  pulseTail: '#22d3ee',
  pulseApi: '#a855f7',
  ground: '#f5f3ec',
}

const { isDark } = useTheme()
const palette: ComputedRef<ScenePalette> = computed(() => (isDark.value ? DARK : LIGHT))

export function useScenePalette() {
  return { palette, isDark }
}
