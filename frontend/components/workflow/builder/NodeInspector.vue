<script setup lang="ts">
/**
 * The builder's right-hand editing panel for the selected step. Renders the
 * fields that matter for the step's kind (PRD 11), including meta-prompting
 * (prompt node) and structured-output (`response_schema`) controls, plus
 * click-to-insert reference chips for `{{steps.*}}` / `{{inputs.*}}` paths.
 */
import { computed, ref } from 'vue'
import type { StepSpec, WorkflowInputField } from '@/composables/useAsyncJobs'
import { availableRefs, type BuilderNode } from '@/composables/useWorkflowSpec'

const props = defineProps<{
  step: StepSpec
  nodes: BuilderNode[]
  inputs: WorkflowInputField[]
}>()

const step = computed(() => props.step)

const MODALITIES = [
  { value: 'chat', label: 'Chat / LLM' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
  { value: 'music', label: 'Music' },
  { value: 'tts', label: 'Speech (TTS)' },
]
const TARGETS = [
  { value: 'image', label: 'Image prompt' },
  { value: 'video', label: 'Video prompt' },
  { value: 'music', label: 'Music brief' },
  { value: 'tts', label: 'Narration line' },
  { value: 'text', label: 'Text prompt' },
]
const OPS = [
  { value: 'passthrough', label: 'Passthrough' },
  { value: 'pluck', label: 'Pluck a field' },
  { value: 'split_lines', label: 'Split lines' },
  { value: 'join', label: 'Join' },
  { value: 'zip', label: 'Zip lists' },
]

// Body conveniences — structured fields that read/write into step.body.
const setBody = (k: string, v: unknown) => { step.value.body = { ...(step.value.body || {}), [k]: v } }
const bodyPrompt = computed({
  get: () => String((step.value.body as { prompt?: unknown })?.prompt ?? ''),
  set: (v: string) => setBody('prompt', v),
})
const bodyInput = computed({
  get: () => String((step.value.body as { input?: unknown })?.input ?? ''),
  set: (v: string) => setBody('input', v),
})
const chatUser = computed({
  get: () => {
    const msgs = (step.value.body as { messages?: { role: string; content: string }[] })?.messages
    const u = msgs?.find((m) => m.role === 'user')
    return u?.content || ''
  },
  set: (v: string) => setBody('messages', [{ role: 'user', content: v }]),
})

// JSON textareas (response_schema, raw body) — local string + parse-on-input.
const schemaText = ref(step.value.response_schema ? JSON.stringify(step.value.response_schema, null, 2) : '')
const schemaError = ref('')
const onSchema = (v: string) => {
  schemaText.value = v
  if (!v.trim()) { delete step.value.response_schema; schemaError.value = ''; return }
  try { step.value.response_schema = JSON.parse(v); schemaError.value = '' }
  catch { schemaError.value = 'Invalid JSON' }
}

const zipText = ref(Array.isArray(step.value.inputs) ? (step.value.inputs as string[]).join('\n') : '')
const onZip = (v: string) => {
  zipText.value = v
  step.value.inputs = v.split('\n').map((l) => l.trim()).filter(Boolean)
}

const upstreamIds = computed(() => props.nodes.filter((n) => n.id !== step.value.id).map((n) => n.id))
const refs = computed(() => availableRefs(step.value, props.nodes, props.inputs))

// Click-to-insert: track the last focused field and splice a ref at the cursor.
let lastFocused: HTMLInputElement | HTMLTextAreaElement | null = null
const remember = (e: FocusEvent) => { lastFocused = e.target as HTMLInputElement | HTMLTextAreaElement }
const insertRef = (r: string) => {
  const el = lastFocused
  if (!el) return
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? el.value.length
  el.value = el.value.slice(0, start) + r + el.value.slice(end)
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.focus()
  const pos = start + r.length
  requestAnimationFrame(() => el.setSelectionRange(pos, pos))
}

const FIELD = 'w-full rounded-md border bg-background px-2.5 py-1.5 text-sm'
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-center justify-between">
      <span class="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">
        {{ step.kind }}
      </span>
      <span class="font-mono text-[11px] text-muted-foreground" title="Step id — use in templates">{{ step.id }}</span>
    </div>

    <label class="block">
      <span class="mb-1 block text-xs font-medium text-muted-foreground">Title</span>
      <input v-model="step.title" :class="FIELD" placeholder="A short label" @focus="remember" >
    </label>

    <!-- prompt (meta-prompting) -->
    <template v-if="step.kind === 'prompt'">
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Writes a prompt for</span>
        <select v-model="step.target" :class="FIELD">
          <option v-for="o in TARGETS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Brief</span>
        <textarea v-model="step.input" rows="3" :class="FIELD" placeholder="what to write a prompt about — supports {{ }}" @focus="remember" />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Extra direction (optional)</span>
        <textarea v-model="step.instructions" rows="2" :class="FIELD" @focus="remember" />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">How many prompts</span>
        <input v-model.number="step.count" type="number" min="1" max="64" :class="FIELD" >
        <span class="mt-1 block text-[11px] text-muted-foreground">&gt; 1 returns a list — feed it into a Fan-out's "over".</span>
      </label>
    </template>

    <!-- inference / map -->
    <template v-else-if="step.kind === 'inference' || step.kind === 'map'">
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Modality</span>
        <select v-model="step.type" :class="FIELD">
          <option v-for="o in MODALITIES" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label v-if="step.kind === 'map'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Fan-out over (a list)</span>
        <input v-model="step.over" :class="FIELD" placeholder="{{steps.prompts.output.prompts}}" @focus="remember" >
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Model (blank = auto)</span>
        <input v-model="step.model" :class="FIELD" placeholder="auto — best available" @focus="remember" >
      </label>
      <!-- per-modality body field -->
      <label v-if="step.type === 'chat'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">User message</span>
        <textarea v-model="chatUser" rows="4" :class="FIELD" placeholder="Ask the model… supports {{ }}" @focus="remember" />
      </label>
      <label v-else-if="step.type === 'tts'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Text to speak</span>
        <textarea v-model="bodyInput" rows="3" :class="FIELD" placeholder="{{item}} or {{steps.script.output}}" @focus="remember" />
      </label>
      <label v-else class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Prompt</span>
        <textarea v-model="bodyPrompt" rows="3" :class="FIELD" placeholder="{{item}} or a literal prompt" @focus="remember" />
      </label>
      <!-- structured output -->
      <label v-if="step.type === 'chat'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Response JSON schema (optional)</span>
        <textarea
:value="schemaText" rows="4" :class="[FIELD, 'font-mono text-xs']"
                  placeholder='{"type":"object","properties":{...}}'
                  @focus="remember" @input="onSchema(($event.target as HTMLTextAreaElement).value)" />
        <span v-if="schemaError" class="mt-1 block text-[11px] text-rose-500">{{ schemaError }}</span>
        <span v-else class="mt-1 block text-[11px] text-muted-foreground">Forces structured output; the reply is parsed into this step's output.</span>
      </label>
    </template>

    <!-- transform -->
    <template v-else-if="step.kind === 'transform'">
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Operation</span>
        <select v-model="step.op" :class="FIELD">
          <option v-for="o in OPS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label v-if="step.op !== 'zip'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Input</span>
        <input v-model="step.input" :class="FIELD" placeholder="{{steps.x.output}}" @focus="remember" >
      </label>
      <label v-if="step.op === 'pluck'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Field to pluck</span>
        <input v-model="step.field" :class="FIELD" placeholder="prompt" @focus="remember" >
      </label>
      <label v-if="step.op === 'join'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Separator</span>
        <input v-model="step.sep" :class="FIELD" placeholder="\n" @focus="remember" >
      </label>
      <label v-if="step.op === 'zip'" class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Lists to pair (one ref per line)</span>
        <textarea
:value="zipText" rows="3" :class="[FIELD, 'font-mono text-xs']"
                  placeholder="{{steps.a.output}}&#10;{{steps.b.output}}"
                  @focus="remember" @input="onZip(($event.target as HTMLTextAreaElement).value)" />
      </label>
    </template>

    <!-- collect -->
    <template v-else-if="step.kind === 'collect'">
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-muted-foreground">Collect from step</span>
        <select v-model="step.from" :class="FIELD">
          <option value="">— pick a step —</option>
          <option v-for="id in upstreamIds" :key="id" :value="id">{{ id }}</option>
        </select>
      </label>
    </template>

    <!-- gate -->
    <template v-else-if="step.kind === 'gate'">
      <p class="rounded-md border border-dashed p-2.5 text-xs text-muted-foreground">
        This step pauses the run for your approval. Connect the steps it should gate into it.
      </p>
    </template>

    <!-- reference chips -->
    <div v-if="refs.length" class="border-t pt-3">
      <span class="mb-1.5 block text-xs font-medium text-muted-foreground">Insert a reference</span>
      <div class="flex flex-wrap gap-1">
        <button
v-for="r in refs" :key="r" type="button"
                class="rounded-full border px-2 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary hover:text-foreground"
                @click="insertRef(r)">{{ r }}</button>
      </div>
      <span class="mt-1.5 block text-[11px] text-muted-foreground">Click a field, then a chip to drop it at the cursor.</span>
    </div>
  </div>
</template>