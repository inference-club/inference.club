<script setup lang="ts">
/**
 * Collapsible per-episode production settings: the pronunciation lexicon
 * (`written = spoken`, one per line) and the Autopilot / pipeline knobs
 * (sampling, retake budget, accept threshold, loudness, trim gaps). Saves a
 * partial `settings` PATCH and shows the backend's error detail inline.
 */
import { ref, watch } from 'vue'
import { CheckCircle2, ChevronDown, Loader2, SlidersHorizontal } from 'lucide-vue-next'
import { useStudio, type EpisodeSettings, type EpisodeSettingsPatch } from '@/composables/useStudio'

const props = defineProps<{ episodeId: number; settings: EpisodeSettings | undefined }>()
const emit = defineEmits<{ (e: 'saved', settings: EpisodeSettings | undefined): void }>()

const studio = useStudio()
const open = ref(false)
const saving = ref(false)
const err = ref<string | null>(null)
const saved = ref(false)

type NumKey = 'temperature' | 'cfg_scale' | 'max_attempts' | 'accept_score' | 'trim_max_gap' | 'trim_gap_threshold'
const FIELDS: { key: NumKey; label: string; step: number; title: string }[] = [
  { key: 'temperature', label: 'Temperature', step: 0.05, title: 'Sampling temperature — higher is more varied' },
  { key: 'cfg_scale', label: 'CFG scale', step: 0.1, title: 'How strictly the voice follows the text' },
  { key: 'max_attempts', label: 'Max attempts', step: 1, title: 'Autopilot retakes per line before flagging it' },
  { key: 'accept_score', label: 'Accept score', step: 0.1, title: 'Take score (0–10) at which Autopilot stops retaking' },
  { key: 'trim_gap_threshold', label: 'Trim gap ≥ (s)', step: 0.05, title: 'Silences at least this long are shortened' },
  { key: 'trim_max_gap', label: 'Max gap (s)', step: 0.05, title: 'Pauses are cut down to this length' },
]

const lexicon = ref('')
const nums = ref<Record<NumKey, number | null>>({
  temperature: null, cfg_scale: null, max_attempts: null, accept_score: null, trim_max_gap: null, trim_gap_threshold: null,
})
const loudnessOn = ref(true)
const loudness = ref<number | null>(-16)

function fromSettings(s: EpisodeSettings | undefined) {
  if (!s) return
  lexicon.value = Object.entries(s.lexicon || {}).map(([w, sp]) => `${w} = ${sp}`).join('\n')
  for (const f of FIELDS) nums.value[f.key] = s[f.key]
  loudnessOn.value = s.loudness_lufs !== null
  loudness.value = s.loudness_lufs ?? -16
}
watch(() => props.settings, fromSettings, { immediate: true })

function parseLexicon(src: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const raw of src.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const i = line.indexOf('=')
    if (i <= 0) throw new Error(`Lexicon line needs "written = spoken": ${line}`)
    const written = line.slice(0, i).trim()
    const spoken = line.slice(i + 1).trim()
    if (!written || !spoken) throw new Error(`Lexicon line needs "written = spoken": ${line}`)
    out[written] = spoken
  }
  return out
}

async function save() {
  err.value = null; saved.value = false
  let patch: EpisodeSettingsPatch
  try {
    patch = { lexicon: parseLexicon(lexicon.value) }
  } catch (e) { err.value = (e as Error).message; return }
  for (const f of FIELDS) {
    const v = nums.value[f.key]
    // Empty input → null → backend resets the key to its default.
    patch[f.key] = typeof v === 'number' && !Number.isNaN(v) ? v : null
  }
  patch.loudness_lufs = loudnessOn.value
    ? (typeof loudness.value === 'number' && !Number.isNaN(loudness.value) ? loudness.value : null)
    : 'off'
  saving.value = true
  try {
    const ep = await studio.updateEpisode(props.episodeId, { settings: patch })
    fromSettings(ep.settings)
    emit('saved', ep.settings)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2800)
  } catch (e) {
    const data = (e as { data?: { detail?: string } })?.data
    err.value = data?.detail || (e instanceof Error ? e.message : 'Failed to save settings')
  } finally { saving.value = false }
}

const inputCls = 'w-24 rounded-md border bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400'
</script>

<template>
  <div class="rounded-xl border bg-background text-sm">
    <button
      type="button" class="flex w-full items-center gap-1.5 px-3 py-2.5 font-medium"
      :aria-expanded="open" @click="open = !open"
    >
      <SlidersHorizontal class="size-4 text-fuchsia-500" /> Production settings
      <span v-if="settings && Object.keys(settings.lexicon || {}).length" class="text-xs font-normal text-muted-foreground">
        · {{ Object.keys(settings.lexicon).length }} lexicon entr{{ Object.keys(settings.lexicon).length === 1 ? 'y' : 'ies' }}
      </span>
      <ChevronDown class="ml-auto size-4 text-muted-foreground transition-transform" :class="open ? 'rotate-180' : ''" />
    </button>

    <div v-if="open" class="space-y-3 border-t px-3 py-3">
      <label class="block space-y-1">
        <span class="text-xs font-medium text-muted-foreground">Lexicon — one <code>written = spoken</code> per line</span>
        <textarea
          v-model="lexicon" rows="4" :disabled="saving" placeholder="Hermes OTel = Hermes Oh-tel"
          class="w-full resize-y rounded-md border bg-transparent px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-sky-400"
        />
        <span class="text-[11px] text-muted-foreground">e.g. <code>Hermes OTel = Hermes Oh-tel</code> — applied to the text sent to the voice model.</span>
      </label>

      <div class="flex flex-wrap gap-3">
        <label v-for="f in FIELDS" :key="f.key" class="flex flex-col gap-1 text-xs text-muted-foreground" :title="f.title">
          {{ f.label }}
          <input v-model.number="nums[f.key]" type="number" :step="f.step" :disabled="saving" :class="inputCls">
        </label>
        <div class="flex flex-col gap-1 text-xs text-muted-foreground" title="Level every clip to this loudness (LUFS)">
          <span class="flex items-center gap-1.5">
            Loudness (LUFS)
            <label class="flex items-center gap-1">
              <input v-model="loudnessOn" type="checkbox" :disabled="saving" class="accent-fuchsia-500"> on
            </label>
          </span>
          <input v-model.number="loudness" type="number" step="0.5" :disabled="saving || !loudnessOn" :class="[inputCls, !loudnessOn ? 'opacity-50' : '']">
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button" :disabled="saving"
          class="flex items-center gap-1 rounded-md bg-fuchsia-500 px-2.5 py-1.5 text-sm font-medium text-white hover:bg-fuchsia-600 disabled:opacity-50"
          @click="save"
        >
          <Loader2 v-if="saving" class="size-4 animate-spin" /> Save settings
        </button>
        <span v-if="saved" class="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 class="size-3.5" /> Saved
        </span>
        <p v-if="err" class="text-xs text-rose-500">{{ err }}</p>
      </div>
    </div>
  </div>
</template>
