<script setup lang="ts">
// Generate square album/playlist cover art and link it to a song (MUSIC
// request) or a collection. Candidates are ordinary IMAGE requests, so
// re-rolls are never lost — they all land in the user's image history.

import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Sparkles, ImagePlus } from 'lucide-vue-next'
import type { ModelInfo } from '@/composables/usePlayground'
import { useCoverArt, type CoverResult } from '@/composables/useCoverArt'
import { useContentSharing } from '@/composables/useContentSharing'

const props = defineProps<{
  open: boolean
  /** 'request' links the cover to a MUSIC request; 'collection' to a playlist. */
  target: { kind: 'request'; id: string | number } | { kind: 'collection'; slug: string }
  /** Seed for the art prompt (song prompt/lyrics or collection name/description). */
  seedPrompt?: string
}>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'updated', coverUrl: string | null): void
}>()

const { listImageModels, listChatModels, improvePrompt, generateCover } = useCoverArt()
const { setRequestCover, setCollectionCover } = useContentSharing()

const imageModels = ref<ModelInfo[]>([])
const chatModels = ref<ModelInfo[]>([])
const model = ref('')
const prompt = ref('')
const improving = ref(false)
const generating = ref(false)
const saving = ref(false)
const candidates = ref<CoverResult[]>([])
const selected = ref<CoverResult | null>(null)
const loadError = ref<string | null>(null)

const seedToPrompt = (seed: string) =>
  `Square album cover art for: ${seed.slice(0, 500)}`

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    prompt.value = props.seedPrompt ? seedToPrompt(props.seedPrompt) : ''
    candidates.value = []
    selected.value = null
    loadError.value = null
    try {
      ;[imageModels.value, chatModels.value] = await Promise.all([
        listImageModels(),
        listChatModels(),
      ])
      if (!model.value && imageModels.value.length) {
        model.value = imageModels.value[0].id
      }
      if (!imageModels.value.length) {
        loadError.value = 'No image-generation model is online right now.'
      }
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : 'Failed to load models'
    }
  },
)

const canImprove = computed(
  () => chatModels.value.length > 0 && prompt.value.trim().length > 0,
)

const onImprove = async () => {
  if (!canImprove.value || improving.value) return
  improving.value = true
  try {
    prompt.value = await improvePrompt(chatModels.value[0].id, prompt.value)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to improve the prompt')
  } finally {
    improving.value = false
  }
}

const onGenerate = async () => {
  if (!model.value || !prompt.value.trim() || generating.value) return
  generating.value = true
  try {
    const result = await generateCover(model.value, prompt.value.trim())
    candidates.value = [result, ...candidates.value]
    selected.value = result
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Cover generation failed')
  } finally {
    generating.value = false
  }
}

const onSave = async () => {
  if (!selected.value || saving.value) return
  saving.value = true
  try {
    if (props.target.kind === 'request') {
      await setRequestCover(props.target.id, selected.value.requestId)
    } else {
      await setCollectionCover(props.target.slug, selected.value.requestId)
    }
    emit('updated', selected.value.url)
    emit('update:open', false)
    toast.success('Cover updated')
  } catch {
    toast.error('Failed to set the cover')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v) => emit('update:open', v)">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>Generate cover art</DialogTitle>
        <DialogDescription>
          Square artwork (1024×1024) generated on the network. Every attempt is
          saved with your images, so nothing is lost when you re-roll.
        </DialogDescription>
      </DialogHeader>

      <div v-if="loadError" class="text-sm text-destructive">{{ loadError }}</div>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <Label>Model</Label>
          <Select v-model="model">
            <SelectTrigger><SelectValue placeholder="Pick an image model" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="m in imageModels" :key="m.id" :value="m.id">
                {{ m.id }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <Label>Prompt</Label>
            <Button
              v-if="chatModels.length"
              variant="ghost"
              size="sm"
              class="h-7 gap-1 px-2 text-xs"
              :disabled="!canImprove || improving"
              @click="onImprove"
            >
              <component :is="improving ? Loader2 : Sparkles" class="size-3.5" :class="improving ? 'animate-spin' : ''" />
              Improve with AI
            </Button>
          </div>
          <Textarea v-model="prompt" rows="3" placeholder="Describe the cover…" />
        </div>

        <Button
          class="w-full gap-2"
          :disabled="!model || !prompt.trim() || generating"
          data-testid="generate-cover"
          @click="onGenerate"
        >
          <component :is="generating ? Loader2 : ImagePlus" class="size-4" :class="generating ? 'animate-spin' : ''" />
          {{ generating ? 'Generating…' : candidates.length ? 'Generate another' : 'Generate' }}
        </Button>

        <div v-if="candidates.length" class="grid grid-cols-3 gap-2">
          <button
            v-for="c in candidates"
            :key="c.requestId"
            type="button"
            class="overflow-hidden rounded-lg border-2 transition-colors"
            :class="selected?.requestId === c.requestId ? 'border-primary' : 'border-transparent hover:border-muted-foreground/40'"
            @click="selected = c"
          >
            <img :src="c.url" class="aspect-square w-full object-cover" alt="Cover candidate" />
          </button>
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="emit('update:open', false)">Cancel</Button>
        <Button :disabled="!selected || saving" @click="onSave">
          <Loader2 v-if="saving" class="size-4 animate-spin" />
          Set as cover
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
