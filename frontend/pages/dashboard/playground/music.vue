<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  AudioLines, ChevronDown, Dices, Loader2, Music2, Sparkles, Square, Wand2,
} from 'lucide-vue-next'
import { useMusicGeneration } from '@/composables/useMusicGeneration'
import {
  useMusicAssist, ASSIST_PRESETS, type SongIdea,
} from '@/composables/useMusicAssist'
import type { ModelInfo } from '@/composables/usePlayground'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.musicGeneration' })

const { listMusicModels, generate } = useMusicGeneration()
const { listChatModels, composeIdeas } = useMusicAssist()
const prefill = usePlaygroundPrefill()

const models = ref<ModelInfo[]>([])
const model = ref('')
const loadingModels = ref(true)
const modelsError = ref('')

// --- inputs ----------------------------------------------------------------
const prompt = ref('')
const lyrics = ref('')

// --- "Write with AI" assist ------------------------------------------------
const chatModels = ref<ModelInfo[]>([])
const assistModel = ref('')
const presetId = ref(ASSIST_PRESETS[0].id)
// The meta-prompt (system message) is seeded from the chosen preset but fully
// editable — picking a preset repopulates it.
const metaPrompt = ref(ASSIST_PRESETS[0].system)
const showAssist = ref(false)
const showMeta = ref(false)
const brief = ref('')
const ideas = ref<SongIdea[]>([])
const composing = ref(false)
let assistController: AbortController | null = null

watch(presetId, (id) => {
  const p = ASSIST_PRESETS.find((x) => x.id === id)
  if (p) metaPrompt.value = p.system
})

const canCompose = computed(() => !!assistModel.value && !composing.value)

const compose = async () => {
  if (!canCompose.value) return
  composing.value = true
  assistController = new AbortController()
  try {
    ideas.value = await composeIdeas(
      { model: assistModel.value, system: metaPrompt.value, description: brief.value, count: 3 },
      assistController.signal,
    )
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Couldn’t generate ideas')
  } finally {
    composing.value = false
    assistController = null
  }
}
const stopCompose = () => assistController?.abort()

const useIdea = (idea: SongIdea) => {
  prompt.value = idea.prompt
  lyrics.value = idea.lyrics
  toast.success('Loaded into the form — tweak and generate')
}

// --- options ---------------------------------------------------------------
const duration = ref(90)
const steps = ref(8)
const guidance = ref(7)
const format = ref('wav')
const randomizeSeed = ref(true)
const seed = ref(0)
const bpm = ref('')
const keyScale = ref('')

// --- run state -------------------------------------------------------------
const running = ref(false)
let controller: AbortController | null = null

// Bumped after each successful generation so the recent-for-this-model strip
// refetches and flashes the song that just finished.
const refreshKey = ref(0)

const canRun = computed(() => !!model.value && !!prompt.value.trim() && !running.value)

const num = (v: string) => {
  const n = Number(v)
  return v.trim() !== '' && !Number.isNaN(n) ? n : undefined
}

const run = async () => {
  if (!canRun.value) return
  running.value = true
  controller = new AbortController()
  const p = prompt.value.trim()
  try {
    const song = await generate(
      {
        model: model.value,
        prompt: p,
        lyrics: lyrics.value.trim() || undefined,
        audio_duration: duration.value,
        inference_steps: steps.value,
        guidance_scale: guidance.value,
        use_random_seed: randomizeSeed.value,
        seed: randomizeSeed.value ? undefined : seed.value,
        audio_format: format.value,
        bpm: num(bpm.value),
        key_scale: keyScale.value.trim() || undefined,
      },
      controller.signal,
    )
    // We play the song from its persisted MUSIC request (in the recent strip),
    // not the transient blob — so release the object URL the client made.
    URL.revokeObjectURL(song.url)
    refreshKey.value++
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string }
    if (err?.name !== 'AbortError') toast.error(err?.message || 'Music generation failed')
  } finally {
    running.value = false
    controller = null
  }
}
const stop = () => controller?.abort()

useSubmitHotkey(run)

// Queue N copies as async jobs (one song per queued job).
const { queue } = useQueueGenerations()
const onQueue = (count: number) => {
  if (!model.value || !prompt.value.trim()) return
  queue(
    '/v1/music/generations',
    {
      model: model.value,
      prompt: prompt.value.trim(),
      lyrics: lyrics.value.trim() || undefined,
      audio_duration: duration.value,
      inference_steps: steps.value,
      guidance_scale: guidance.value,
      use_random_seed: randomizeSeed.value,
      seed: randomizeSeed.value ? undefined : seed.value,
      audio_format: format.value,
      bpm: num(bpm.value),
      key_scale: keyScale.value.trim() || undefined,
    },
    count,
    'song',
  )
}

const fmtDuration = (s: number) =>
  s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s}s`

// Populate the form from a "Reproduce in playground" handoff, if any.
const applyPrefill = () => {
  const p = prefill.take('MUSIC')
  if (!p) return
  if (typeof p.prompt === 'string') prompt.value = p.prompt
  if (typeof p.lyrics === 'string') lyrics.value = p.lyrics
  if (typeof p.audio_duration === 'number') duration.value = p.audio_duration
  if (typeof p.inference_steps === 'number') steps.value = p.inference_steps
  if (typeof p.guidance_scale === 'number') guidance.value = p.guidance_scale
  if (typeof p.audio_format === 'string') format.value = p.audio_format
  if (typeof p.use_random_seed === 'boolean') randomizeSeed.value = p.use_random_seed
  if (typeof p.seed === 'number') seed.value = p.seed
  if (p.bpm != null) bpm.value = String(p.bpm)
  if (typeof p.key_scale === 'string') keyScale.value = p.key_scale
  if (typeof p.model === 'string' && models.value.some((m) => m.id === p.model)) model.value = p.model
}

onMounted(async () => {
  try {
    models.value = await listMusicModels()
    if (models.value.length) {
      const wanted = String(useRoute().query.model || '')
      model.value = (wanted && models.value.find((m) => m.id === wanted)?.id) || models.value[0].id
      applyPrefill()
    } else {
      modelsError.value =
        'No music-generation models are available to you yet. Run an agent with a service of type: music (e.g. ACE-Step) to add one.'
    }
  } catch (e: unknown) {
    modelsError.value = (e as { message?: string })?.message || 'Failed to load models'
  } finally {
    loadingModels.value = false
  }
  // Load chat models for the AI assist (best-effort — assist just hides if none).
  try {
    chatModels.value = await listChatModels()
    if (chatModels.value.length) assistModel.value = chatModels.value[0].id
  } catch {
    /* assist stays unavailable */
  }
})

onBeforeUnmount(() => {
  assistController?.abort()
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Music2 class="h-6 w-6" /> Music generation
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Describe a song — a style, mood, and instruments — add optional lyrics, and generate music.
        </p>
      </div>
      <Select v-model="model" :disabled="loadingModels || !models.length">
        <SelectTrigger class="w-full sm:w-[18rem] font-mono text-xs">
          <SelectValue :placeholder="loadingModels ? 'Loading models…' : 'Select a model'" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="m in models" :key="m.id" :value="m.id" class="font-mono text-xs">
            {{ m.id }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="modelsError" class="p-3 mb-4 bg-muted text-muted-foreground rounded text-sm">
      {{ modelsError }}
    </div>

    <div v-if="models.length" class="grid lg:grid-cols-[1fr_18rem] gap-4 items-start">
      <!-- Composer -->
      <div class="min-w-0 space-y-3">
        <!-- Write with AI: have an LLM compose a prompt + lyrics -->
        <Card v-if="chatModels.length" class="p-4 border-primary/30 bg-primary/[0.03]" :class="showAssist ? 'space-y-3' : ''">
          <button
            type="button"
            class="flex w-full items-center gap-2 text-left"
            :aria-expanded="showAssist"
            @click="showAssist = !showAssist"
          >
            <Sparkles class="size-4 text-primary" />
            <span class="text-sm font-semibold">Write with AI</span>
            <span class="text-[11px] text-muted-foreground">Let an LLM draft a prompt &amp; lyrics</span>
            <ChevronDown
              class="ml-auto size-4 text-muted-foreground transition-transform"
              :class="showAssist ? 'rotate-0' : '-rotate-90'"
            />
          </button>

          <template v-if="showAssist">
          <div class="grid grid-cols-2 gap-2">
            <div>
              <Label class="text-xs text-muted-foreground">Writer model</Label>
              <Select v-model="assistModel">
                <SelectTrigger class="mt-1 h-8 text-xs font-mono"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="m in chatModels" :key="m.id" :value="m.id" class="font-mono text-xs">
                    {{ m.id }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label class="text-xs text-muted-foreground">Style</Label>
              <Select v-model="presetId">
                <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="p in ASSIST_PRESETS" :key="p.id" :value="p.id" class="text-sm">
                    {{ p.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label class="text-xs text-muted-foreground">What do you want? (optional)</Label>
            <Textarea
              v-model="brief"
              rows="2"
              placeholder="e.g. a bit of reggae with lyrics about wanting to dance — leave blank to surprise me"
              class="mt-1 resize-none text-sm"
            />
          </div>

          <!-- Editable meta-prompt (the exact system message sent to the LLM) -->
          <div>
            <button
              type="button"
              class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              @click="showMeta = !showMeta"
            >
              <ChevronDown class="size-3 transition-transform" :class="showMeta ? 'rotate-0' : '-rotate-90'" />
              Edit system prompt
            </button>
            <Textarea
              v-if="showMeta"
              v-model="metaPrompt"
              rows="8"
              class="mt-1 resize-y text-xs font-mono"
            />
          </div>

          <div class="flex flex-wrap items-center gap-x-2 gap-y-2">
            <span class="text-[11px] text-muted-foreground">{{ brief.trim() ? 'Composes from your brief' : 'Surprise me' }}</span>
            <div class="ml-auto flex items-center gap-2">
              <Button v-if="composing" variant="destructive" size="sm" class="gap-2" @click="stopCompose">
                <Square class="size-3.5" /> Stop
              </Button>
              <Button size="sm" :disabled="!canCompose" class="gap-2" @click="compose">
                <component
                  :is="composing ? Loader2 : (brief.trim() ? Wand2 : Dices)"
                  class="size-3.5"
                  :class="composing ? 'animate-spin' : ''"
                />
                {{ brief.trim() ? 'Compose ideas' : 'Surprise me' }}
              </Button>
            </div>
          </div>

          <!-- Generated idea candidates -->
          <div v-if="ideas.length" class="space-y-2 pt-1">
            <div
              v-for="(idea, i) in ideas"
              :key="i"
              class="rounded-lg border bg-background p-3 space-y-1.5"
            >
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium truncate">{{ idea.title || `Idea ${i + 1}` }}</p>
                <Button size="sm" variant="outline" class="ml-auto h-7 gap-1.5 text-xs shrink-0" @click="useIdea(idea)">
                  Use this
                </Button>
              </div>
              <p class="text-xs text-muted-foreground line-clamp-2">{{ idea.prompt }}</p>
              <p v-if="idea.lyrics" class="text-[11px] text-muted-foreground/80 line-clamp-2 whitespace-pre-line font-mono">
                {{ idea.lyrics }}
              </p>
              <p v-else class="text-[11px] italic text-muted-foreground/70">Instrumental</p>
            </div>
          </div>
          </template>
        </Card>

        <Card class="p-4 space-y-3">
          <div>
            <Label class="text-xs text-muted-foreground">Prompt</Label>
            <Textarea
              v-model="prompt"
              rows="3"
              placeholder="e.g. dreamy lo-fi hip-hop with mellow piano, soft vinyl crackle, 80 BPM"
              class="mt-1 resize-none text-sm"
            />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Lyrics (optional)</Label>
            <Textarea
              v-model="lyrics"
              rows="4"
              placeholder="[verse]&#10;Type lyrics here, or leave blank for an instrumental…"
              class="mt-1 resize-none text-sm font-mono"
            />
          </div>
          <div class="flex flex-wrap items-center gap-x-2 gap-y-2">
            <span class="text-xs text-muted-foreground">{{ prompt.length }} chars</span>
            <div class="ml-auto flex items-center gap-2">
              <GenerationSharingPicker compact />
              <Button v-if="running" variant="destructive" class="gap-2" @click="stop">
                <Square class="size-4" /> Stop
              </Button>
              <GenerateButton
                :disabled="!canRun"
                :queue-disabled="!model || !prompt.trim()"
                :running="running"
                :icon="AudioLines"
                label="Generate"
                noun="song"
                @generate="run"
                @queue="onQueue"
              />
            </div>
          </div>
        </Card>

        <!-- In-flight notice -->
        <Card v-if="running" class="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 class="size-4 animate-spin shrink-0" />
          <span class="flex-1">Composing your song — this usually takes under a minute…</span>
          <ElapsedTimer :running="running" class="shrink-0 font-medium text-foreground" />
        </Card>

        <!-- Recent songs for this model (the just-finished one flashes in) -->
        <RecentGenerations :model="model" type="MUSIC" :refresh-key="refreshKey" title="Recent songs" />
      </div>

      <!-- Options -->
      <Card class="p-4 space-y-4">
        <div>
          <Label class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Options</Label>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Duration: {{ fmtDuration(duration) }}</Label>
          <Input v-model.number="duration" type="range" min="10" max="240" step="5" class="mt-1 w-full" />
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Inference steps: {{ steps }}</Label>
          <Input v-model.number="steps" type="range" min="1" max="50" step="1" class="mt-1 w-full" />
          <p class="mt-1 text-[11px] text-muted-foreground">More steps = higher quality, slower.</p>
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Guidance: {{ guidance }}</Label>
          <Input v-model.number="guidance" type="range" min="0" max="15" step="0.5" class="mt-1 w-full" />
        </div>

        <div>
          <Label class="text-xs text-muted-foreground">Format</Label>
          <Select v-model="format">
            <SelectTrigger class="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="wav" class="text-sm">WAV</SelectItem>
              <SelectItem value="flac" class="text-sm">FLAC</SelectItem>
              <SelectItem value="opus" class="text-sm">Opus</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div>
            <Label class="text-xs text-muted-foreground">BPM</Label>
            <Input v-model="bpm" placeholder="auto" class="mt-1 h-8 text-sm" />
          </div>
          <div>
            <Label class="text-xs text-muted-foreground">Key</Label>
            <Input v-model="keyScale" placeholder="e.g. C Major" class="mt-1 h-8 text-sm" />
          </div>
        </div>

        <div class="border-t pt-4 space-y-2">
          <div class="flex items-center justify-between">
            <Label for="rand-seed" class="text-sm flex items-center gap-1.5">
              <Dices class="size-3.5" /> Randomize seed
            </Label>
            <Switch id="rand-seed" v-model="randomizeSeed" />
          </div>
          <div v-if="!randomizeSeed">
            <Label class="text-xs text-muted-foreground">Seed</Label>
            <Input v-model.number="seed" type="number" class="mt-1 h-8 text-sm" />
          </div>
        </div>

        <p class="text-[11px] text-muted-foreground border-t pt-3">
          Songs are generated on a provider's GPU and stored on inference.club.
        </p>
      </Card>
    </div>
  </div>
</template>
