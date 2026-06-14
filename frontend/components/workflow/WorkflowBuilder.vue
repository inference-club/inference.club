<script setup lang="ts">
/**
 * Visual workflow builder (PRD 11): an editable Vue Flow canvas where you drag
 * in nodes, wire them together, configure each in the inspector, then save it
 * as your own reusable workflow or run it. The graph serializes to the exact
 * `spec` the PRD 10 engine runs — builder, templates and AI authoring all share
 * one format.
 */
import { computed, markRaw, ref } from 'vue'
import { VueFlow, applyNodeChanges, applyEdgeChanges, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { Plus, Save, Play, AlertTriangle, Settings2, Loader2, Trash2 } from 'lucide-vue-next'
import BuilderNode from '@/components/workflow/builder/BuilderNode.vue'
import NodeInspector from '@/components/workflow/builder/NodeInspector.vue'
import { useAsyncJobs, type SavedWorkflow, type WorkflowSpec, type WorkflowInputField } from '@/composables/useAsyncJobs'
import {
  specToGraph, graphToSpec, blankStep, validateGraph,
  STEP_KINDS, type BuilderNode as BNode, type BuilderEdge,
} from '@/composables/useWorkflowSpec'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps<{
  id?: number | null
  initial: { name: string; description: string; spec: WorkflowSpec }
}>()

const { createWorkflow, updateWorkflow, runSavedWorkflow } = useAsyncJobs()
const nodeTypes = { builder: markRaw(BuilderNode) }

// --- state -------------------------------------------------------------------
const wfId = ref<number | null>(props.id ?? null)
const name = ref(props.initial.name || 'Untitled workflow')
const description = ref(props.initial.description || '')
const inputs = ref<WorkflowInputField[]>(props.initial.spec.inputs || [])

const removeNode = (id: string) => {
  nodes.value = nodes.value.filter((n) => n.id !== id)
  edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
  if (selectedId.value === id) selectedId.value = null
}

const graph0 = specToGraph(props.initial.spec)
const nodes = ref<BNode[]>(graph0.nodes.map((n) => ({ ...n, data: { ...n.data, onDelete: removeNode } })))
const edges = ref<BuilderEdge[]>(graph0.edges.map(decorate))
const selectedId = ref<string | null>(null)

function decorate(e: BuilderEdge): BuilderEdge {
  return { ...e, markerEnd: MarkerType.ArrowClosed, style: { strokeWidth: 1.5 } }
}

const selectedStep = computed(() => nodes.value.find((n) => n.id === selectedId.value)?.data.step || null)
const errors = computed(() => validateGraph(nodes.value, edges.value))

// --- canvas events -----------------------------------------------------------
const onNodesChange = (changes: unknown[]) => {
  // Position / dimensions / selection only — deletion is via the node button.
  nodes.value = applyNodeChanges(changes as never, nodes.value as never) as never
}
const onEdgesChange = (changes: unknown[]) => {
  edges.value = applyEdgeChanges(changes as never, edges.value as never) as never
}
const onConnect = (conn: { source: string; target: string }) => {
  if (conn.source === conn.target) return
  const id = `${conn.source}->${conn.target}`
  if (edges.value.some((e) => e.id === id)) return
  edges.value = [...edges.value, decorate({ id, source: conn.source, target: conn.target })]
}

let counter = 0
const addNode = (kind: (typeof STEP_KINDS)[number]['kind']) => {
  const existing = new Set(nodes.value.map((n) => n.id))
  let id = ''
  do { id = `${kind}_${++counter}` } while (existing.has(id))
  const step = blankStep(kind, id)
  const x = 80 + (nodes.value.length % 4) * 120
  const y = 80 + Math.floor(nodes.value.length / 4) * 80
  nodes.value = [...nodes.value, { id, type: 'builder', position: { x, y }, data: { step, onDelete: removeNode } }]
  selectedId.value = id
}

const onNodeClick = (e: { node: { id: string } }) => { selectedId.value = e.node.id }
const onPaneClick = () => { selectedId.value = null }

// --- input-schema editor (workflow settings) ---------------------------------
const addInput = () => {
  inputs.value = [...inputs.value, { name: `input${inputs.value.length + 1}`, label: 'New input', type: 'text' }]
}
const removeInput = (i: number) => { inputs.value = inputs.value.filter((_, idx) => idx !== i) }

// --- save / run --------------------------------------------------------------
const saving = ref(false)
const saveError = ref('')
const toSpec = (): WorkflowSpec => graphToSpec(nodes.value, edges.value, { name: name.value, inputs: inputs.value })

const save = async (): Promise<boolean> => {
  saving.value = true
  saveError.value = ''
  try {
    const payload = { name: name.value, description: description.value, spec: toSpec() }
    if (wfId.value) {
      await updateWorkflow(wfId.value, payload)
    } else {
      const wf = await createWorkflow(payload) as SavedWorkflow
      wfId.value = wf.id
      // Move to the canonical edit URL so reloads land back here.
      window.history.replaceState({}, '', `/dashboard/workflows/${wf.id}/edit`)
    }
    return true
  } catch (e: unknown) {
    saveError.value = (e as { data?: { error?: { message?: string } } })?.data?.error?.message
      || (e as Error)?.message || 'Save failed'
    return false
  } finally {
    saving.value = false
  }
}

const runModal = ref(false)
const runForm = ref<Record<string, string | number>>({})
const running = ref(false)
const openRun = async () => {
  if (errors.value.length) return
  if (!(await save())) return
  if (!inputs.value.length) { void doRun() ; return }
  const f: Record<string, string | number> = {}
  for (const inp of inputs.value) f[inp.name] = inp.default ?? ''
  runForm.value = f
  runModal.value = true
}
const doRun = async () => {
  if (!wfId.value) return
  running.value = true
  try {
    const run = await runSavedWorkflow(wfId.value, { ...runForm.value }, name.value)
    await navigateTo(`/dashboard/queue/runs/${run.id}`)
  } catch (e: unknown) {
    saveError.value = (e as { data?: { error?: { message?: string } } })?.data?.error?.message
      || (e as Error)?.message || 'Run failed'
  } finally {
    running.value = false
    runModal.value = false
  }
}
</script>

<template>
  <div class="flex h-[calc(100vh-7rem)] flex-col">
    <!-- toolbar -->
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <input
v-model="name" class="min-w-0 flex-1 rounded-md border bg-background px-3 py-1.5 text-sm font-semibold"
             placeholder="Workflow name" >
      <span
v-if="errors.length"
            class="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-600 dark:text-amber-400"
            :title="errors.map((e) => e.message).join('\n')">
        <AlertTriangle class="size-3.5" /> {{ errors.length }} {{ errors.length === 1 ? 'issue' : 'issues' }}
      </span>
      <button
class="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              :disabled="saving" @click="save">
        <Loader2 v-if="saving" class="size-4 animate-spin" /><Save v-else class="size-4" /> Save
      </button>
      <button
class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              :disabled="!!errors.length || running" @click="openRun">
        <Play class="size-4" /> Run
      </button>
    </div>
    <p v-if="saveError" class="mb-2 text-sm text-rose-500">{{ saveError }}</p>

    <div class="flex min-h-0 flex-1 gap-3">
      <!-- palette -->
      <div class="flex w-44 shrink-0 flex-col gap-1.5 overflow-y-auto rounded-lg border bg-background p-2">
        <span class="px-1 pb-1 text-xs font-semibold text-muted-foreground">Add a step</span>
        <button
v-for="k in STEP_KINDS" :key="k.kind"
                class="flex flex-col items-start rounded-md border px-2 py-1.5 text-left text-sm hover:border-primary hover:bg-muted/50"
                :title="k.hint" @click="addNode(k.kind)">
          <span class="flex items-center gap-1.5 font-medium"><Plus class="size-3.5" /> {{ k.label }}</span>
          <span class="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{{ k.hint }}</span>
        </button>
      </div>

      <!-- canvas -->
      <div class="min-w-0 flex-1 overflow-hidden rounded-lg border bg-muted/20">
        <VueFlow
          :nodes="nodes" :edges="edges" :node-types="nodeTypes"
          :min-zoom="0.2" :max-zoom="2" :delete-key-code="null"
          :default-edge-options="{ type: 'smoothstep' }" fit-view-on-init
          @nodes-change="onNodesChange" @edges-change="onEdgesChange"
          @connect="onConnect" @node-click="onNodeClick" @pane-click="onPaneClick"
        >
          <Background :gap="20" pattern-color="#94a3b833" />
          <Controls />
        </VueFlow>
      </div>

      <!-- inspector / settings -->
      <div class="w-80 shrink-0 overflow-y-auto rounded-lg border bg-background p-3">
        <NodeInspector v-if="selectedStep" :key="selectedStep.id" :step="selectedStep" :nodes="nodes" :inputs="inputs" />
        <div v-else class="space-y-3 text-sm">
          <h3 class="flex items-center gap-1.5 font-semibold"><Settings2 class="size-4" /> Workflow settings</h3>
          <label class="block">
            <span class="mb-1 block text-xs font-medium text-muted-foreground">Description</span>
            <textarea v-model="description" rows="2" class="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" />
          </label>
          <div>
            <div class="mb-1 flex items-center justify-between">
              <span class="text-xs font-medium text-muted-foreground">Inputs (run-time parameters)</span>
              <button class="rounded p-0.5 hover:bg-muted" title="Add input" @click="addInput"><Plus class="size-3.5" /></button>
            </div>
            <p v-if="!inputs.length" class="rounded-md border border-dashed p-2 text-[11px] text-muted-foreground">
              No inputs. Add one and reference it as <code v-pre>{{inputs.name}}</code> in your steps.
            </p>
            <div v-for="(inp, i) in inputs" :key="i" class="mb-2 rounded-md border p-2">
              <div class="mb-1 flex items-center gap-1">
                <input v-model="inp.name" class="w-0 flex-1 rounded border bg-background px-1.5 py-1 font-mono text-xs" placeholder="name" >
                <button class="rounded p-0.5 text-muted-foreground hover:text-rose-500" @click="removeInput(i)"><Trash2 class="size-3.5" /></button>
              </div>
              <input v-model="inp.label" class="mb-1 w-full rounded border bg-background px-1.5 py-1 text-xs" placeholder="Label" >
              <div class="flex items-center gap-1.5">
                <select v-model="inp.type" class="flex-1 rounded border bg-background px-1.5 py-1 text-xs">
                  <option value="text">text</option><option value="textarea">textarea</option>
                  <option value="number">number</option><option value="select">select</option>
                </select>
                <label class="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <input v-model="inp.required" type="checkbox" > required
                </label>
              </div>
            </div>
          </div>
          <p class="rounded-md border border-dashed p-2 text-[11px] text-muted-foreground">
            Tip: drag from a node's right dot to another node's left dot to connect them. Click a node to edit it.
          </p>
        </div>
      </div>
    </div>

    <!-- run inputs modal -->
    <div v-if="runModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="runModal = false">
      <div class="w-full max-w-md rounded-xl border bg-background p-5 shadow-xl">
        <h3 class="mb-3 text-lg font-semibold">Run “{{ name }}”</h3>
        <form class="space-y-3" @submit.prevent="doRun">
          <div v-for="inp in inputs" :key="inp.name">
            <label class="mb-1 block text-sm font-medium">{{ inp.label }}<span v-if="inp.required" class="text-rose-500"> *</span></label>
            <textarea v-if="inp.type === 'textarea'" v-model="runForm[inp.name]" rows="3" class="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            <input v-else-if="inp.type === 'number'" v-model.number="runForm[inp.name]" type="number" :min="inp.min" :max="inp.max" class="w-full rounded-md border bg-background px-3 py-2 text-sm" >
            <input v-else v-model="runForm[inp.name]" type="text" :placeholder="inp.placeholder" class="w-full rounded-md border bg-background px-3 py-2 text-sm" >
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <button type="button" class="rounded-md border px-3 py-2 text-sm hover:bg-muted" @click="runModal = false">Cancel</button>
            <button type="submit" :disabled="running" class="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
              <Loader2 v-if="running" class="size-4 animate-spin" /> Run
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
