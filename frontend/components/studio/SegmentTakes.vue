<script setup lang="ts">
/**
 * A segment's takes, one row each: pick it, see its seed / take score /
 * attempt # / pace, and save it as a voice sample (optionally cloning it for
 * the rest of the episode).
 */
import { onBeforeUnmount, ref } from 'vue'
import { BookmarkPlus, CheckCircle2, Loader2 } from 'lucide-vue-next'
import { useStudio, type Segment, type Variant } from '@/composables/useStudio'

const props = defineProps<{ segment: Segment; busy: boolean }>()
const emit = defineEmits<{ (e: 'pick', v: Variant): void; (e: 'changed'): void }>()

const studio = useStudio()
const formFor = ref<number | null>(null)
const speakerName = ref('Narrator')
const useForEpisode = ref(true)
const makeDefault = ref(false)
const saving = ref(false)
const err = ref<string | null>(null)
const savedMsg = ref<string | null>(null)
let savedTimer: ReturnType<typeof setTimeout> | null = null
onBeforeUnmount(() => { if (savedTimer) clearTimeout(savedTimer) })

function openForm(v: Variant) {
  formFor.value = formFor.value === v.id ? null : v.id
  err.value = null
}

async function saveVoice(v: Variant) {
  if (!speakerName.value.trim()) { err.value = 'Give the voice a speaker name'; return }
  saving.value = true; err.value = null
  try {
    const voice = await studio.saveVariantAsVoice(props.segment.id, v.id, {
      speaker_name: speakerName.value.trim(),
      is_default: makeDefault.value,
      use_for_episode: useForEpisode.value,
    })
    formFor.value = null
    savedMsg.value = `Saved as voice “${voice.speaker_name}”${useForEpisode.value ? ' — this episode now clones it' : ''}`
    if (savedTimer) clearTimeout(savedTimer)
    savedTimer = setTimeout(() => { savedMsg.value = null }, 4000)
    emit('changed')
  } catch (e) {
    const data = (e as { data?: { detail?: string } })?.data
    err.value = data?.detail || (e instanceof Error ? e.message : 'Failed to save voice')
  } finally { saving.value = false }
}

const seedOf = (v: Variant) => v.seed ?? v.grade?.seed ?? null
const fmt1 = (n: number | undefined) => (typeof n === 'number' ? n.toFixed(1) : '')
</script>

<template>
  <div class="space-y-1 pt-1">
    <div class="flex items-center gap-2">
      <span class="text-[11px] text-muted-foreground">Takes:</span>
      <span v-if="savedMsg" class="ml-auto flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 class="size-3.5" /> {{ savedMsg }}
      </span>
    </div>
    <div
v-for="(v, i) in segment.variants" :key="v.id" class="rounded-md border text-[11px]"
         :class="v.id === segment.selected_variant_id ? 'border-sky-400' : ''">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1 px-1.5 py-1">
        <button
          type="button" :disabled="busy || v.id === segment.selected_variant_id"
          class="rounded px-1.5 py-0.5 font-medium hover:bg-muted disabled:cursor-default"
          :class="v.id === segment.selected_variant_id ? 'text-sky-600 dark:text-sky-400' : ''"
          :title="v.id === segment.selected_variant_id ? 'Selected take' : 'Use this take'"
          @click="emit('pick', v)"
        >
          Take {{ segment.variants.length - i }}
        </button>
        <span v-if="v.grade?.take_score != null" class="text-muted-foreground" :title="v.grade.reason">
          score <b :class="v.grade.accepted ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'">{{ fmt1(v.grade.take_score) }}</b>
        </span>
        <span v-else-if="v.grade" class="text-muted-foreground" :title="v.grade.reason">grade {{ fmt1(v.grade.score) }}</span>
        <span v-if="v.grade?.attempt != null" class="text-muted-foreground">attempt #{{ v.grade.attempt }}</span>
        <span v-if="v.grade?.wps != null" class="text-muted-foreground" title="Pace in words per second">{{ v.grade.wps.toFixed(2) }} wps</span>
        <span v-if="seedOf(v) != null" class="font-mono text-muted-foreground">seed {{ seedOf(v) }}</span>
        <span v-if="v.duration_seconds" class="text-muted-foreground">{{ v.duration_seconds.toFixed(1) }}s</span>
        <button
          v-if="v.audio_url" type="button" :disabled="busy || saving"
          class="ml-auto flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-medium hover:bg-muted disabled:opacity-50"
          title="Save this take as a voice sample to clone from" @click="openForm(v)"
        >
          <BookmarkPlus class="size-3 text-fuchsia-500" /> Save as voice
        </button>
      </div>
      <form v-if="formFor === v.id" class="flex flex-wrap items-center gap-2 border-t px-1.5 py-1.5" @submit.prevent="saveVoice(v)">
        <label class="flex items-center gap-1 text-muted-foreground">
          Speaker
          <input
v-model="speakerName" type="text" :disabled="saving"
                 class="w-28 rounded-md border bg-transparent px-1.5 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-sky-400">
        </label>
        <label class="flex items-center gap-1 text-muted-foreground">
          <input v-model="useForEpisode" type="checkbox" :disabled="saving" class="accent-fuchsia-500"> use for this episode
        </label>
        <label class="flex items-center gap-1 text-muted-foreground">
          <input v-model="makeDefault" type="checkbox" :disabled="saving" class="accent-fuchsia-500"> make default
        </label>
        <button
type="submit" :disabled="saving"
                class="flex items-center gap-1 rounded-md bg-fuchsia-500 px-2 py-0.5 font-medium text-white hover:bg-fuchsia-600 disabled:opacity-50">
          <Loader2 v-if="saving" class="size-3 animate-spin" /> Save
        </button>
        <button type="button" :disabled="saving" class="rounded-md border px-2 py-0.5 font-medium hover:bg-muted" @click="formFor = null">
          Cancel
        </button>
        <p v-if="err" class="w-full text-rose-500">{{ err }}</p>
      </form>
    </div>
  </div>
</template>
