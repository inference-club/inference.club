<script setup lang="ts">
// Narrate: paste a link or some text, press one button, get it read aloud in
// your voice. This page is the front door; the work and the result live on
// /dashboard/narrate/<id>.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { ArrowRight, AudioLines, Link2, Loader2, Mic, Trash2, TriangleAlert, CircleCheck } from 'lucide-vue-next'
import { useNarration, clock, type Narration } from '@/composables/useNarration'
import { useStudio, type StudioVoices } from '@/composables/useStudio'
import { formatRelative } from '@/utils/inference'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.narrate' })

const { t } = useI18n()
const router = useRouter()
const api = useNarration()
const studio = useStudio()

const input = ref('')
const starting = ref(false)
const error = ref('')
const items = ref<Narration[]>([])
const loading = ref(true)
const voices = ref<StudioVoices | null>(null)
const voiceId = ref<number | null>(null)

const isLink = computed(() => /^(https?:\/\/)?[\w.-]+\.[a-z]{2,}(\/\S*)?$/i.test(input.value.trim()))
const words = computed(() => (input.value.trim() ? input.value.trim().split(/\s+/).length : 0))
const usable = computed(() => voices.value?.samples.filter((s) => s.has_transcript) ?? [])
const canClone = computed(() => !!voices.value?.voices.some((v) => v.voice_cloning))

const load = async () => {
  try {
    items.value = await api.list()
  } catch {
    /* the list is a convenience; the form still works */
  } finally {
    loading.value = false
  }
}
let timer: ReturnType<typeof setInterval> | null = null
onMounted(async () => {
  load()
  // Keep the list fresh while something is still being narrated.
  timer = setInterval(() => { if (items.value.some((n) => n.narration.active)) load() }, 4000)
  try {
    voices.value = await studio.listVoices()
  } catch {
    voices.value = { voices: [], samples: [] }
  }
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const start = async () => {
  if (!input.value.trim() || starting.value) return
  starting.value = true
  error.value = ''
  try {
    const n = await api.start(input.value, { voiceSampleId: voiceId.value })
    router.push(`/dashboard/narrate/${n.id}`)
  } catch (e) {
    const detail = (e as { data?: { detail?: string } })?.data?.detail
    error.value = detail || t('narrate.startFailed')
    starting.value = false
  }
}

const remove = async (n: Narration) => {
  try {
    await api.remove(n.id)
    items.value = items.value.filter((x) => x.id !== n.id)
  } catch {
    toast.error(t('narrate.deleteFailed'))
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 py-6 sm:px-6 sm:py-10">
    <header class="mb-6">
      <h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
        <AudioLines class="size-7 text-primary" /> {{ t('narrate.title') }}
      </h1>
      <p class="mt-2 text-muted-foreground">{{ t('narrate.subtitle') }}</p>
    </header>

    <!-- One box, one button. -->
    <form class="rounded-2xl border bg-card p-3 shadow-sm sm:p-4" @submit.prevent="start">
      <label for="narrate-input" class="sr-only">{{ t('narrate.inputLabel') }}</label>
      <textarea
        id="narrate-input"
        v-model="input"
        :rows="isLink || !input ? 3 : 8"
        class="block w-full resize-y rounded-xl border-0 bg-transparent p-2 text-base outline-none placeholder:text-muted-foreground/70"
        :placeholder="t('narrate.placeholder')"
        data-testid="narrate-input"
        @keydown.meta.enter.prevent="start"
        @keydown.ctrl.enter.prevent="start"
      />
      <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 border-t pt-3">
        <span v-if="input.trim()" class="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Link2 v-if="isLink" class="size-3.5" />
          {{ isLink ? t('narrate.detectedLink') : t('narrate.detectedText', { n: words }, words) }}
        </span>
        <label class="ml-auto inline-flex min-w-0 items-center gap-2 text-sm">
          <Mic class="size-4 shrink-0 text-muted-foreground" />
          <span class="sr-only">{{ t('narrate.voice') }}</span>
          <select
            v-model="voiceId"
            class="h-9 min-w-0 max-w-[11rem] truncate rounded-md border bg-background px-2 text-sm"
            data-testid="narrate-voice"
          >
            <option :value="null">{{ usable.length ? t('narrate.voiceDefault') : t('narrate.voiceNone') }}</option>
            <option v-for="s in usable" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <Button type="submit" class="gap-2" :disabled="!input.trim() || starting" data-testid="narrate-start">
          <component :is="starting ? Loader2 : AudioLines" class="size-4" :class="starting ? 'animate-spin' : ''" />
          {{ t('narrate.go') }}
        </Button>
      </div>
    </form>
    <p v-if="error" class="mt-3 flex items-start gap-2 text-sm text-destructive" role="alert">
      <TriangleAlert class="mt-0.5 size-4 shrink-0" /> {{ error }}
    </p>
    <p v-else-if="voices && !canClone" class="mt-3 flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
      <TriangleAlert class="mt-0.5 size-4 shrink-0" /> {{ t('narrate.noVoiceModel') }}
    </p>
    <p v-else-if="voices && !usable.length" class="mt-3 text-sm text-muted-foreground">
      {{ t('narrate.noSampleHint') }}
      <NuxtLink to="/dashboard/playground/voice-cloning" class="underline">{{ t('narrate.addVoice') }}</NuxtLink>
    </p>

    <!-- What happens, in four words. -->
    <ol class="mt-6 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <li v-for="(step, i) in ['read', 'plan', 'voice', 'mix']" :key="step" class="rounded-xl border bg-muted/30 p-3">
        <span class="font-mono text-xs text-muted-foreground">{{ i + 1 }}</span>
        <p class="font-medium">{{ t(`narrate.steps.${step}.title`) }}</p>
        <p class="mt-0.5 text-xs text-muted-foreground">{{ t(`narrate.steps.${step}.body`) }}</p>
      </li>
    </ol>

    <!-- Earlier narrations -->
    <section class="mt-10">
      <h2 class="mb-3 text-lg font-semibold">{{ t('narrate.yours') }}</h2>
      <div v-if="loading" class="space-y-2">
        <div v-for="i in 2" :key="i" class="h-20 animate-pulse rounded-xl bg-muted" />
      </div>
      <p v-else-if="!items.length" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
        {{ t('narrate.empty') }}
      </p>
      <ul v-else class="space-y-2">
        <li v-for="n in items" :key="n.id" class="group flex min-w-0 items-center gap-3 rounded-xl border bg-card p-2.5 hover:border-primary/40">
          <NuxtLink :to="`/dashboard/narrate/${n.id}`" class="flex min-w-0 flex-1 items-center gap-3" :data-testid="`narration-${n.id}`">
            <img
              v-if="n.cover_image_url"
              :src="n.cover_image_url"
              alt=""
              class="h-14 w-24 shrink-0 rounded-lg border object-cover"
              loading="lazy"
            />
            <span v-else class="flex h-14 w-24 shrink-0 items-center justify-center rounded-lg border bg-muted">
              <AudioLines class="size-5 text-muted-foreground" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ n.title }}</span>
              <span class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                <span v-if="n.narration.active" class="inline-flex items-center gap-1 text-primary">
                  <Loader2 class="size-3 animate-spin" />
                  {{ t(`narrate.stage.${n.narration.stage}`) }} · {{ Math.round(n.narration.fraction * 100) }}%
                </span>
                <span v-else-if="n.narration.stage === 'done'" class="inline-flex items-center gap-1">
                  <CircleCheck class="size-3 text-emerald-500" /> {{ clock(n.audio_seconds) }}
                </span>
                <span v-else class="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                  <TriangleAlert class="size-3" /> {{ t(`narrate.stage.${n.narration.stage}`) }}
                </span>
                <span v-if="n.source?.author">{{ n.source.author }}</span>
                <span>{{ formatRelative(n.created_on) }}</span>
              </span>
            </span>
            <ArrowRight class="size-4 shrink-0 text-muted-foreground" />
          </NuxtLink>
          <button
            type="button"
            class="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-destructive"
            :aria-label="t('narrate.delete')"
            :title="t('narrate.delete')"
            @click="remove(n)"
          >
            <Trash2 class="size-4" />
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
