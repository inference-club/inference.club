// Shared chrome finish for the 3D jack variants. Polished metal: full
// metalness, env map does the shading; a whisper of indigo keeps it on-brand.
import { computed } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'

export function useChromeMaterials() {
  const { isDark } = useScenePalette()
  const chromeMat = computed(() => ({
    color: isDark.value ? '#dde2f2' : '#d4d9e8',
    metalness: 1,
    roughness: 0.16,
    envMapIntensity: isDark.value ? 1.05 : 1.3,
  }))
  const ballMat = computed(() => ({ ...chromeMat.value, roughness: 0.08 }))
  return { chromeMat, ballMat }
}
