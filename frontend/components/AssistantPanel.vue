<script setup lang="ts">
// The assistant panel: a side sheet (full width on phones) reachable from every
// dashboard page. Type or talk; each thing the assistant does shows as a card
// with a one-line result, and generated media appears in place when it lands.
// State and the wire protocol live in stores/assistant.ts.

import { nextTick, ref, watch } from 'vue'
import {
  Sparkles, Mic, Square, ArrowUp, Check, AlertCircle, Loader2, Trash2,
  Volume2, VolumeX, Clock,
} from 'lucide-vue-next'
import { useAssistantStore } from '@/stores/assistant'
import { useAudioRecorder } from '@/composables/useAudioRecorder'

const { t, te } = useI18n()
const assistant = useAssistantStore()
const recorder = useAudioRecorder()

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const micError = ref(false)

const suggestions = ['s1', 's2', 's3', 's4'] as const

const toolLabel = (name: string) =>
  te(`assistant.tools.${name}`) ? t(`assistant.tools.${name}`) : name.replace(/_/g, ' ')

const submit = () => {
  const text = draft.value
  draft.value = ''
  void assistant.send(text)
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}

const toggleMic = async () => {
  micError.value = false
  if (recorder.recording.value) {
    recorder.stop()
    return
  }
  assistant.stopSpeaking()
  try {
    assistant.status = 'listening'
    const audio = await recorder.start()
    await assistant.transcribeAndSend(audio.blob, audio.ext)
  } catch {
    micError.value = true
    assistant.status = 'idle'
  }
}

// Keep the newest activity in view.
watch(
  () => [assistant.turns.length, assistant.turns.at(-1)?.text, assistant.turns.at(-1)?.actions.length],
  () => nextTick(() => scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' })),
)

// ⌘J / Ctrl+J opens the assistant from anywhere.
const onGlobalKey = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
    e.preventDefault()
    assistant.toggle()
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <Sheet v-model:open="assistant.open">
    <SheetContent
      side="right"
      class="flex w-full flex-col gap-0 p-0 sm:max-w-md"
      data-testid="assistant-panel"
    >
      <SheetHeader class="border-b px-4 py-3 pr-12">
        <SheetTitle class="flex items-center gap-2 text-base">
          <Sparkles class="size-4 text-primary" />
          {{ t('assistant.title') }}
        </SheetTitle>
        <SheetDescription class="sr-only">{{ t('assistant.intro') }}</SheetDescription>
        <div class="flex min-w-0 items-center gap-2 pt-1">
          <Select v-model="assistant.model">
            <SelectTrigger class="h-8 min-w-0 flex-1 text-xs" :aria-label="t('assistant.model')">
              <SelectValue :placeholder="t('assistant.modelAuto')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="m in assistant.models" :key="m" :value="m" class="text-xs">
                {{ m }}
              </SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="icon"
            class="size-8 shrink-0"
            :class="assistant.speakReplies ? 'text-primary' : 'text-muted-foreground'"
            :title="t('assistant.speakReplies')"
            :aria-pressed="assistant.speakReplies"
            data-testid="assistant-speak"
            @click="assistant.speakReplies = !assistant.speakReplies"
          >
            <Volume2 v-if="assistant.speakReplies" class="size-4" />
            <VolumeX v-else class="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="size-8 shrink-0 text-muted-foreground"
            :title="t('assistant.clear')"
            :disabled="!assistant.turns.length"
            @click="assistant.clear()"
          >
            <Trash2 class="size-4" />
          </Button>
        </div>
      </SheetHeader>

      <div ref="scroller" class="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <!-- Empty state: what you can say -->
        <div v-if="!assistant.turns.length" class="space-y-3">
          <p class="text-sm text-muted-foreground">{{ t('assistant.intro') }}</p>
          <div class="flex flex-col gap-2">
            <button
              v-for="s in suggestions"
              :key="s"
              type="button"
              class="rounded-lg border px-3 py-2 text-left text-sm hover:bg-accent"
              @click="assistant.send(t(`assistant.suggestions.${s}`))"
            >
              {{ t(`assistant.suggestions.${s}`) }}
            </button>
          </div>
        </div>

        <template v-for="(turn, i) in assistant.turns" :key="i">
          <!-- What the person said -->
          <div v-if="turn.role === 'user'" class="flex justify-end">
            <p class="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm break-words text-primary-foreground">
              <Mic v-if="turn.spoken" class="mr-1 inline size-3.5 align-[-2px] opacity-80" />{{ turn.text }}
            </p>
          </div>

          <!-- What the assistant did, then what it said -->
          <div v-else class="space-y-2" :data-testid="`assistant-turn-${i}`">
            <div
              v-for="action in turn.actions"
              :key="action.id"
              class="rounded-lg border bg-card px-3 py-2 text-sm"
              data-testid="assistant-action"
            >
              <div class="flex items-start gap-2">
                <Loader2 v-if="!action.done" class="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground" />
                <Check v-else-if="action.ok" class="mt-0.5 size-4 shrink-0 text-emerald-500" />
                <AlertCircle v-else class="mt-0.5 size-4 shrink-0 text-destructive" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    {{ toolLabel(action.name) }}
                  </p>
                  <p v-if="action.summary" class="break-words" :class="action.ok === false ? 'text-destructive' : ''">
                    {{ action.summary }}
                  </p>
                </div>
              </div>

              <div v-if="action.media.length" class="mt-2 grid grid-cols-2 gap-2">
                <template v-for="m in action.media" :key="m.url">
                  <img v-if="m.kind === 'image'" :src="m.url" class="rounded-md border" alt="" loading="lazy" />
                  <video v-else-if="m.kind === 'video'" :src="m.url" controls playsinline class="col-span-2 rounded-md border" />
                  <audio v-else-if="m.kind === 'audio'" :src="m.url" controls class="col-span-2 w-full" />
                </template>
              </div>

              <!-- Queued work: follows each job until its result lands -->
              <div v-if="action.jobs.length" class="mt-2 space-y-2">
                <div
                  v-for="job in action.jobs"
                  :key="job.id"
                  class="rounded-md border border-dashed px-2 py-1.5 text-xs"
                  data-testid="assistant-job"
                >
                  <div class="flex items-center gap-1.5 text-muted-foreground">
                    <Check v-if="job.status === 'PROCESSED'" class="size-3.5 text-emerald-500" />
                    <AlertCircle v-else-if="job.status === 'FAILED' || job.status === 'CANCELED'" class="size-3.5 text-destructive" />
                    <Clock v-else-if="job.status === 'QUEUED'" class="size-3.5" />
                    <Loader2 v-else class="size-3.5 animate-spin" />
                    <span class="min-w-0 truncate">
                      {{ job.title || job.kind }} · {{ t(`assistant.job.${job.status}`) }}
                    </span>
                  </div>
                  <template v-for="m in job.media" :key="m.url">
                    <img v-if="m.kind === 'image'" :src="m.url" class="mt-1.5 rounded-md border" alt="" loading="lazy" />
                    <video v-else-if="m.kind === 'video'" :src="m.url" controls playsinline class="mt-1.5 w-full rounded-md border" />
                    <audio v-else-if="m.kind === 'audio'" :src="m.url" controls class="mt-1.5 w-full" />
                  </template>
                  <p v-if="job.error" class="mt-1 break-words text-destructive">{{ job.error }}</p>
                </div>
              </div>
            </div>

            <p v-if="turn.text" class="text-sm break-words whitespace-pre-wrap" data-testid="assistant-reply">
              {{ turn.text }}
            </p>
            <p v-if="turn.error" class="flex items-start gap-1.5 text-sm text-destructive">
              <AlertCircle class="mt-0.5 size-4 shrink-0" />
              <span class="min-w-0 break-words">{{ turn.error === 'no-stt' ? t('assistant.noStt') : turn.error }}</span>
            </p>
            <p v-if="!turn.done && !turn.text && !turn.actions.length" class="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 class="size-4 animate-spin" /> {{ t('assistant.status.working') }}
            </p>
          </div>
        </template>
      </div>

      <!-- Composer -->
      <div class="border-t p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <p
          v-if="assistant.status !== 'idle' || micError"
          class="mb-2 flex items-center gap-1.5 text-xs"
          :class="micError ? 'text-destructive' : 'text-muted-foreground'"
          aria-live="polite"
        >
          <template v-if="micError">{{ t('assistant.micDenied') }}</template>
          <template v-else>
            <span v-if="assistant.status === 'listening'" class="size-2 animate-pulse rounded-full bg-red-500" />
            <Loader2 v-else class="size-3.5 animate-spin" />
            {{ t(`assistant.status.${assistant.status}`) }}
          </template>
        </p>
        <div class="flex items-end gap-2">
          <Textarea
            v-model="draft"
            rows="1"
            class="max-h-32 min-h-10 min-w-0 flex-1 resize-none"
            :placeholder="t('assistant.placeholder')"
            data-testid="assistant-input"
            @keydown="onKeydown"
          />
          <Button
            v-if="recorder.supported.value"
            :variant="recorder.recording.value ? 'destructive' : 'outline'"
            size="icon"
            class="size-10 shrink-0 rounded-full"
            :title="recorder.recording.value ? t('assistant.stopListening') : t('assistant.talk')"
            :disabled="assistant.busy"
            data-testid="assistant-mic"
            @click="toggleMic"
          >
            <Square v-if="recorder.recording.value" class="size-4" />
            <Mic v-else class="size-4" />
          </Button>
          <Button
            v-if="assistant.busy || assistant.status === 'speaking'"
            size="icon"
            variant="secondary"
            class="size-10 shrink-0 rounded-full"
            :title="t('assistant.stop')"
            @click="assistant.stop()"
          >
            <Square class="size-4" />
          </Button>
          <Button
            v-else
            size="icon"
            class="size-10 shrink-0 rounded-full"
            :title="t('assistant.send')"
            :disabled="!draft.trim()"
            data-testid="assistant-send"
            @click="submit"
          >
            <ArrowUp class="size-4" />
          </Button>
        </div>
      </div>
    </SheetContent>
  </Sheet>
</template>
