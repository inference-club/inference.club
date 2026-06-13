<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  AudioLines,
  Loader2,
  Mic,
  Pencil,
  Plus,
  Square,
  Star,
  Trash2,
  Upload,
  Users,
  Wand2,
  X,
} from 'lucide-vue-next'
import { useVoiceCloning, type Speaker, type VoiceSample } from '@/composables/useVoiceCloning'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app' })

const vc = useVoiceCloning()
const recorder = useAudioRecorder()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

const samples = ref<VoiceSample[]>([])
const speakers = computed<Speaker[]>(() => vc.groupBySpeaker(samples.value))
const loadingSamples = ref(false)

const text = ref('')
const twoSpeakers = ref(false)
const speakerS1 = ref('none') // voice-sample id as string, or 'none'
const speakerS2 = ref('none')

// Advanced Dia sampling controls (defaults match the Dia server).
const adv = ref(false)
const cfgScale = ref(3.0)
const temperature = ref(1.8)
const topP = ref(0.95)
const cfgTopK = ref(45)
const speed = ref(1.0)
const seed = ref(-1)
const maxTokens = ref(3072)

const running = ref(false)
let controller: AbortController | null = null
const refreshKey = ref(0)
const lastAudio = ref<{ url: string; seed: string | null } | null>(null)

const canRun = computed(() => !!model.value && !!text.value.trim() && !running.value)

// Flat options for the speaker pickers, labeled by speaker + variation.
const sampleOptions = computed(() =>
  samples.value.map((s) => ({
    id: String(s.id),
    label:
      s.speaker_name +
      (s.label ? ` · ${s.label}` : s.is_default ? '' : ' (variation)') +
      (s.transcript.trim() ? '' : ' — no transcript'),
  })),
)

const loadSamples = async () => {
  loadingSamples.value = true
  try {
    samples.value = await vc.listSamples()
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loadingSamples.value = false
  }
}

const insertTag = (tag: string) => {
  text.value = (text.value ? text.value.replace(/\s*$/, '') + '\n' : '') + tag + ' '
}

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const speakersMap: Record<string, number> = {}
  if (speakerS1.value !== 'none') speakersMap.S1 = Number(speakerS1.value)
  if (twoSpeakers.value && speakerS2.value !== 'none') speakersMap.S2 = Number(speakerS2.value)
  try {
    const audio = await vc.generate(
      {
        model: model.value,
        input: text.value.trim(),
        speakers: Object.keys(speakersMap).length ? speakersMap : undefined,
        cfg_scale: cfgScale.value,
        temperature: temperature.value,
        top_p: topP.value,
        cfg_filter_top_k: cfgTopK.value,
        speed_factor: speed.value,
        seed: seed.value,
        max_new_tokens: maxTokens.value,
      },
      controller.signal,
    )
    if (lastAudio.value) URL.revokeObjectURL(lastAudio.value.url)
    lastAudio.value = { url: audio.url, seed: audio.seed }
    refreshKey.value++
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Voice generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

onMounted(async () => {
  try {
    models.value = await vc.listVoiceModels()
    if (models.value.length) model.value = models.value[0].id
    else
      modelsError.value =
        'No voice-cloning models are available to you yet. Run the Dia service (a tts service with the voice-cloning feature) to add one.'
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
  await loadSamples()
})

// --- Manage voices (library) --------------------------------------------
const manageOpen = ref(false)
const addSpeaker = ref('')
const addLabel = ref('')
const addTranscript = ref('')
const addPending = ref<{ blob: Blob; name: string; url: string } | null>(null)
const addBusy = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

const setPending = (blob: Blob, name: string) => {
  if (addPending.value) URL.revokeObjectURL(addPending.value.url)
  addPending.value = { blob, name, url: URL.createObjectURL(blob) }
}
const clearPending = () => {
  if (addPending.value) URL.revokeObjectURL(addPending.value.url)
  addPending.value = null
}
const onFiles = (e: Event) => {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setPending(f, f.name)
  if (fileInput.value) fileInput.value.value = ''
}
const onDrop = (e: DragEvent) => {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && (f.type.startsWith('audio/') || f.type.startsWith('video/'))) setPending(f, f.name)
  else toast.error('Please drop an audio file')
}
const toggleMic = async () => {
  if (recorder.recording.value) {
    recorder.stop()
    return
  }
  try {
    const rec = await recorder.start()
    setPending(rec.blob, `recording.${rec.ext}`)
  } catch {
    toast.error('Microphone access was denied')
  }
}
const submitSample = async () => {
  if (!addPending.value || !addSpeaker.value.trim()) {
    toast.error('Add a speaker name and an audio clip')
    return
  }
  addBusy.value = true
  try {
    await vc.createSample({
      audio: addPending.value.blob,
      filename: addPending.value.name,
      speaker_name: addSpeaker.value.trim(),
      label: addLabel.value.trim() || undefined,
      transcript: addTranscript.value.trim() || undefined,
      is_default: !speakers.value.find((s) => s.name === addSpeaker.value.trim()),
    })
    toast.success('Voice sample added' + (addTranscript.value.trim() ? '' : ' — transcribing…'))
    if (addPending.value) URL.revokeObjectURL(addPending.value.url)
    addPending.value = null
    addLabel.value = ''
    addTranscript.value = ''
    await loadSamples()
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    addBusy.value = false
  }
}

const editingId = ref<number | null>(null)
const editTranscript = ref('')
const startEdit = (s: VoiceSample) => {
  editingId.value = s.id
  editTranscript.value = s.transcript
}
const saveEdit = async (s: VoiceSample) => {
  try {
    await vc.updateSample(s.id, { transcript: editTranscript.value })
    editingId.value = null
    await loadSamples()
  } catch (e) {
    toast.error((e as Error).message)
  }
}
const setDefault = async (s: VoiceSample) => {
  try {
    await vc.updateSample(s.id, { is_default: true })
    await loadSamples()
  } catch (e) {
    toast.error((e as Error).message)
  }
}
const retranscribe = async (s: VoiceSample) => {
  try {
    toast.info('Transcribing…')
    await vc.transcribeSample(s.id)
    await loadSamples()
    toast.success('Transcribed')
  } catch (e) {
    toast.error((e as Error).message)
  }
}
const removeSample = async (s: VoiceSample) => {
  try {
    await vc.deleteSample(s.id)
    await loadSamples()
  } catch (e) {
    toast.error((e as Error).message)
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Wand2 class="h-6 w-6" /> Voice cloning
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Clone a voice from your samples and speak any script. Use [S1]/[S2] for dialogue.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Dialog v-model:open="manageOpen">
          <DialogTrigger as-child>
            <Button variant="outline" class="gap-2">
              <Users class="size-4" /> Manage voices
            </Button>
          </DialogTrigger>
          <DialogContent class="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Voice sample library</DialogTitle>
            </DialogHeader>

            <!-- Add a sample -->
            <Card class="p-3 space-y-3">
              <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Add a sample
              </Label>
              <div
                class="rounded-xl border-2 border-dashed transition-colors p-4 text-center"
                :class="dragOver ? 'border-primary bg-accent/40' : 'border-border'"
                @dragover.prevent="dragOver = true"
                @dragleave.prevent="dragOver = false"
                @drop.prevent="onDrop"
              >
                <template v-if="addPending">
                  <div class="flex items-center gap-3">
                    <div class="min-w-0 flex-1 text-left">
                      <p class="text-sm font-medium truncate">{{ addPending.name }}</p>
                      <audio :src="addPending.url" controls class="w-full h-9 mt-1" />
                    </div>
                    <Button variant="ghost" size="icon" class="shrink-0" @click="clearPending">
                      <X class="size-4" />
                    </Button>
                  </div>
                </template>
                <template v-else>
                  <Upload class="size-7 mx-auto mb-2 text-muted-foreground opacity-60" />
                  <p class="text-sm text-muted-foreground">
                    Drag an audio clip here, or
                    <button class="text-primary underline" @click="fileInput?.click()">browse</button>
                    / record
                  </p>
                  <input
                    ref="fileInput"
                    type="file"
                    accept="audio/*,video/mp4,video/webm"
                    class="hidden"
                    @change="onFiles"
                  />
                </template>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <Button
                  v-if="recorder.supported.value"
                  variant="outline"
                  size="sm"
                  class="gap-2"
                  :class="recorder.recording.value ? 'text-red-500 border-red-300' : ''"
                  @click="toggleMic"
                >
                  <component :is="recorder.recording.value ? Square : Mic" class="size-4" />
                  {{ recorder.recording.value ? 'Stop' : 'Record' }}
                </Button>
                <Input v-model="addSpeaker" placeholder="Speaker name" class="h-8 w-40 text-sm" />
                <Input v-model="addLabel" placeholder="Variation (optional)" class="h-8 w-44 text-sm" />
              </div>
              <Textarea
                v-model="addTranscript"
                rows="2"
                placeholder="Transcript (leave blank to auto-fill via speech-to-text)…"
                class="resize-none text-sm"
              />
              <div class="flex justify-end">
                <Button size="sm" class="gap-2" :disabled="addBusy" @click="submitSample">
                  <component :is="addBusy ? Loader2 : Plus" class="size-4" :class="addBusy ? 'animate-spin' : ''" />
                  Add sample
                </Button>
              </div>
            </Card>

            <!-- Existing speakers -->
            <div v-if="loadingSamples" class="text-sm text-muted-foreground py-3">Loading…</div>
            <div v-else-if="!speakers.length" class="text-sm text-muted-foreground py-3">
              No voice samples yet. Add one above to start cloning.
            </div>
            <div v-for="sp in speakers" :key="sp.name" class="space-y-2">
              <div class="text-sm font-semibold flex items-center gap-2">
                {{ sp.name }}
                <span class="text-xs text-muted-foreground font-normal">
                  {{ sp.samples.length }} sample{{ sp.samples.length === 1 ? '' : 's' }}
                </span>
              </div>
              <div
                v-for="s in sp.samples"
                :key="s.id"
                class="rounded-lg border p-2 space-y-2"
              >
                <div class="flex items-center gap-2">
                  <Badge v-if="s.is_default" variant="secondary" class="gap-1">
                    <Star class="size-3" /> default
                  </Badge>
                  <span v-if="s.label" class="text-xs text-muted-foreground">{{ s.label }}</span>
                  <span v-if="!s.transcript.trim()" class="text-xs text-amber-600">needs transcript</span>
                  <div class="ml-auto flex items-center gap-1">
                    <Button v-if="!s.is_default" variant="ghost" size="icon" title="Set as default" @click="setDefault(s)">
                      <Star class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="Re-transcribe" @click="retranscribe(s)">
                      <Wand2 class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="Edit transcript" @click="startEdit(s)">
                      <Pencil class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="Delete" @click="removeSample(s)">
                      <Trash2 class="size-4 text-destructive" />
                    </Button>
                  </div>
                </div>
                <audio v-if="s.audio_url" :src="s.audio_url" controls class="w-full h-8" />
                <template v-if="editingId === s.id">
                  <Textarea v-model="editTranscript" rows="2" class="resize-none text-sm" />
                  <div class="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" @click="editingId = null">Cancel</Button>
                    <Button size="sm" @click="saveEdit(s)">Save</Button>
                  </div>
                </template>
                <p v-else-if="s.transcript.trim()" class="text-xs text-muted-foreground line-clamp-2">
                  {{ s.transcript }}
                </p>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <Select v-model="model" :disabled="loadingModels || !models.length">
          <SelectTrigger class="w-[16rem] font-mono text-xs">
            <SelectValue :placeholder="loadingModels ? 'Loading models…' : 'Select a model'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="m in models" :key="m.id" :value="m.id" class="font-mono text-xs">
              {{ m.id }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-muted text-muted-foreground rounded text-sm">
      {{ modelsError }}
    </div>

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_18rem] gap-4 items-start">
      <!-- Composer -->
      <div class="space-y-3">
        <Card class="p-4 space-y-3">
          <Textarea
            v-model="text"
            rows="5"
            placeholder="Type a line to speak. For dialogue, tag lines with [S1] and [S2]…"
            class="resize-none text-sm"
          />
          <div v-if="twoSpeakers" class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">Insert tag:</span>
            <Button variant="outline" size="sm" class="h-7" @click="insertTag('[S1]')">[S1]</Button>
            <Button variant="outline" size="sm" class="h-7" @click="insertTag('[S2]')">[S2]</Button>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ text.length }} characters</span>
            <ElapsedTimer :running="running" class="text-xs text-muted-foreground" />
            <div class="ml-auto flex items-center gap-2">
              <GenerationSharingPicker />
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <Button :disabled="!canRun" class="gap-2" @click="run">
                <component
                  :is="running ? Loader2 : AudioLines"
                  class="size-4"
                  :class="running ? 'animate-spin' : ''"
                />
                Generate
              </Button>
            </div>
          </div>
        </Card>

        <Card v-if="lastAudio" class="p-3">
          <Label class="text-xs text-muted-foreground">Latest result{{ lastAudio.seed ? ` · seed ${lastAudio.seed}` : '' }}</Label>
          <audio :src="lastAudio.url" controls autoplay class="w-full h-9 mt-1" />
        </Card>

        <RecentGenerations :model="model" type="VOICE" :refresh-key="refreshKey" title="Recent voices" />
      </div>

      <!-- Voices + controls -->
      <Card class="p-4 space-y-4">
        <div class="flex items-center justify-between">
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Voices</Label>
          <div class="flex items-center gap-2">
            <Label for="two-spk" class="text-xs text-muted-foreground">Two speakers</Label>
            <Switch id="two-spk" v-model="twoSpeakers" />
          </div>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Speaker 1 (S1)</Label>
          <Select v-model="speakerS1">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue placeholder="Dia default" /></SelectTrigger>
            <SelectContent class="max-h-72">
              <SelectItem value="none" class="text-xs">— Dia default voice —</SelectItem>
              <SelectItem v-for="o in sampleOptions" :key="o.id" :value="o.id" class="text-xs">
                {{ o.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div v-if="twoSpeakers">
          <Label class="text-xs text-muted-foreground">Speaker 2 (S2)</Label>
          <Select v-model="speakerS2">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue placeholder="Dia default" /></SelectTrigger>
            <SelectContent class="max-h-72">
              <SelectItem value="none" class="text-xs">— Dia default voice —</SelectItem>
              <SelectItem v-for="o in sampleOptions" :key="o.id" :value="o.id" class="text-xs">
                {{ o.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <p v-if="!samples.length" class="text-[11px] text-muted-foreground">
          No voice samples yet — open <b>Manage voices</b> to add one. Without a sample, Dia uses its
          own default voice.
        </p>

        <!-- Advanced -->
        <button
          class="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          @click="adv = !adv"
        >
          {{ adv ? '▾' : '▸' }} Advanced
        </button>
        <div v-if="adv" class="space-y-3">
          <div>
            <Label class="text-xs text-muted-foreground">CFG scale ({{ cfgScale }})</Label>
            <Input v-model.number="cfgScale" type="number" step="0.1" min="1" max="5" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Temperature ({{ temperature }})</Label>
            <Input v-model.number="temperature" type="number" step="0.1" min="0.1" max="2" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Top-p ({{ topP }})</Label>
            <Input v-model.number="topP" type="number" step="0.05" min="0.1" max="1" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">CFG top-k ({{ cfgTopK }})</Label>
            <Input v-model.number="cfgTopK" type="number" step="1" min="1" max="100" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Speed ({{ speed }}×)</Label>
            <Input v-model.number="speed" type="number" step="0.05" min="0.5" max="2" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Max new tokens</Label>
            <Input v-model.number="maxTokens" type="number" step="64" min="256" max="4096" class="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Seed (-1 = random)</Label>
            <Input v-model.number="seed" type="number" step="1" class="h-8 text-sm mt-1" />
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
