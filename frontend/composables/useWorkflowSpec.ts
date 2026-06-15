/**
 * Pure helpers that convert between a workflow `spec` (what the backend engine
 * runs) and a Vue Flow graph (what the builder edits), plus client-side
 * validation that mirrors the server's. Keeping these pure keeps the builder
 * component small and makes them unit-testable. (PRD 11)
 */
import dagre from '@dagrejs/dagre'
import type { StepSpec, StepKind, WorkflowSpec } from '@/composables/useAsyncJobs'

export interface BuilderNode {
  id: string
  type: 'builder'
  position: { x: number; y: number }
  data: { step: StepSpec }
}
export interface BuilderEdge {
  id: string
  source: string
  target: string
  markerEnd?: unknown
  style?: Record<string, unknown>
}

export interface SpecError {
  stepId?: string
  message: string
}

export const STEP_KINDS: { kind: StepKind; label: string; hint: string }[] = [
  { kind: 'prompt', label: 'Prompt', hint: 'An LLM writes a prompt for the next step' },
  { kind: 'inference', label: 'Inference', hint: 'Run one generation (image, video, chat…)' },
  { kind: 'map', label: 'Fan-out', hint: 'Run one job per item of a list' },
  { kind: 'transform', label: 'Transform', hint: 'Reshape data (split, sections, subtitles, join, pluck, zip)' },
  { kind: 'collect', label: 'Collect', hint: 'Gather a fan-out back into a list' },
  { kind: 'gate', label: 'Human gate', hint: 'Pause for your approval' },
]

const NODE_W = 240
const NODE_H = 132
const STEP_REF_RE = /steps\.([A-Za-z0-9_-]+)/g

/** Step ids referenced by a step's templates (e.g. `{{steps.outline.output}}`),
 * excluding its own id — the implicit data edges. */
export function referencedSteps(step: StepSpec): string[] {
  const blob = JSON.stringify(step)
  const found = new Set<string>()
  let m: RegExpExecArray | null
  while ((m = STEP_REF_RE.exec(blob))) found.add(m[1])
  found.delete(step.id)
  return [...found]
}

/** A fresh, valid-by-default step of the given kind. */
export function blankStep(kind: StepKind, id: string): StepSpec {
  const base: StepSpec = { id, kind, title: defaultTitle(kind) }
  switch (kind) {
    case 'prompt':
      return { ...base, target: 'image', input: '', count: 1 }
    case 'inference':
      return { ...base, type: 'image', body: { prompt: '' } }
    case 'map':
      return { ...base, type: 'image', over: '', body: { prompt: '{{item}}' } }
    case 'transform':
      return { ...base, op: 'passthrough', input: '' }
    case 'collect':
      return { ...base, from: '' }
    case 'gate':
      return base
  }
}

function defaultTitle(kind: StepKind): string {
  return { prompt: 'Write a prompt', inference: 'Generate', map: 'Fan-out',
    transform: 'Transform', collect: 'Collect', gate: 'Review' }[kind]
}

/** Lay nodes out left→right by dependency depth (same engine the run viewer
 * uses), for specs that carry no saved positions. */
function autoLayout(steps: StepSpec[], edges: BuilderEdge[]): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90, marginx: 24, marginy: 24 })
  for (const s of steps) g.setNode(s.id, { width: NODE_W, height: NODE_H })
  for (const e of edges) g.setEdge(e.source, e.target)
  dagre.layout(g)
  const out: Record<string, { x: number; y: number }> = {}
  for (const s of steps) {
    const n = g.node(s.id)
    out[s.id] = { x: n.x - NODE_W / 2, y: n.y - NODE_H / 2 }
  }
  return out
}

function edgeId(source: string, target: string) {
  return `${source}->${target}`
}

/** Build the Vue Flow graph (nodes + edges) from a saved/forked spec. Edges are
 * the union of explicit `depends_on` and template references. */
export function specToGraph(spec: WorkflowSpec): { nodes: BuilderNode[]; edges: BuilderEdge[] } {
  const steps = spec.steps || []
  const ids = new Set(steps.map((s) => s.id))
  const edgeSet = new Map<string, BuilderEdge>()
  for (const s of steps) {
    const deps = new Set<string>([...(s.depends_on || []), ...referencedSteps(s)])
    for (const dep of deps) {
      if (ids.has(dep) && dep !== s.id) {
        edgeSet.set(edgeId(dep, s.id), { id: edgeId(dep, s.id), source: dep, target: s.id })
      }
    }
  }
  const edges = [...edgeSet.values()]
  const saved = spec.layout || {}
  const auto = autoLayout(steps, edges)
  const nodes: BuilderNode[] = steps.map((s) => ({
    id: s.id,
    type: 'builder',
    position: saved[s.id] || auto[s.id] || { x: 0, y: 0 },
    data: { step: { ...s } },
  }))
  return { nodes, edges }
}

/** Serialize the live graph back into a runnable/saveable spec. `depends_on` is
 * recomputed from the edges; node positions are captured into `layout`. */
export function graphToSpec(
  nodes: BuilderNode[],
  edges: BuilderEdge[],
  meta: { name?: string; inputs?: WorkflowSpec['inputs'] },
): WorkflowSpec {
  const depsByTarget = new Map<string, Set<string>>()
  for (const e of edges) {
    if (!depsByTarget.has(e.target)) depsByTarget.set(e.target, new Set())
    depsByTarget.get(e.target)!.add(e.source)
  }
  const layout: Record<string, { x: number; y: number }> = {}
  const steps: StepSpec[] = nodes.map((n) => {
    const step = { ...n.data.step }
    const deps = [...(depsByTarget.get(n.id) || [])]
    if (deps.length) step.depends_on = deps
    else delete step.depends_on
    layout[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) }
    return step
  })
  const spec: WorkflowSpec = { steps, layout }
  if (meta.name) spec.name = meta.name
  if (meta.inputs && meta.inputs.length) spec.inputs = meta.inputs
  return spec
}

/** Client-side validation mirroring the server's `validate_spec`, so problems
 * surface in the builder before a save/run round-trip. */
export function validateGraph(nodes: BuilderNode[], edges: BuilderEdge[]): SpecError[] {
  const errors: SpecError[] = []
  if (!nodes.length) {
    errors.push({ message: 'Add at least one step.' })
    return errors
  }
  const ids = new Set(nodes.map((n) => n.id))
  for (const n of nodes) {
    const s = n.data.step
    if (s.kind === 'inference' || s.kind === 'map') {
      if (!s.type) errors.push({ stepId: s.id, message: `${s.id}: pick a modality.` })
    }
    if (s.kind === 'map' && !String(s.over || '').trim()) {
      errors.push({ stepId: s.id, message: `${s.id}: a fan-out needs an "over" list.` })
    }
    if (s.kind === 'collect' && !String(s.from || '').trim()) {
      errors.push({ stepId: s.id, message: `${s.id}: collect needs a source step.` })
    }
    if (s.kind === 'prompt' && !String(s.input || '').trim()) {
      errors.push({ stepId: s.id, message: `${s.id}: a prompt step needs a brief.` })
    }
    // Referenced steps must exist.
    for (const ref of referencedSteps(s)) {
      if (!ids.has(ref)) errors.push({ stepId: s.id, message: `${s.id}: references unknown step "${ref}".` })
    }
  }
  if (hasCycle(nodes, edges)) errors.push({ message: 'The graph has a cycle — steps must flow forward.' })
  return errors
}

function hasCycle(nodes: BuilderNode[], edges: BuilderEdge[]): boolean {
  const adj = new Map<string, string[]>()
  for (const n of nodes) adj.set(n.id, [])
  for (const e of edges) adj.get(e.source)?.push(e.target)
  const state = new Map<string, number>() // 0=unseen,1=in-stack,2=done
  const visit = (id: string): boolean => {
    state.set(id, 1)
    for (const nxt of adj.get(id) || []) {
      const st = state.get(nxt) || 0
      if (st === 1) return true
      if (st === 0 && visit(nxt)) return true
    }
    state.set(id, 2)
    return false
  }
  for (const n of nodes) if ((state.get(n.id) || 0) === 0 && visit(n.id)) return true
  return false
}

/** Available `{{ }}` reference paths for autocomplete in the inspector: every
 * upstream step's output plus declared inputs. */
export function availableRefs(
  step: StepSpec,
  nodes: BuilderNode[],
  inputs: WorkflowSpec['inputs'],
): string[] {
  const refs: string[] = []
  for (const f of inputs || []) refs.push(`{{inputs.${f.name}}}`)
  for (const n of nodes) {
    if (n.id === step.id) continue
    const k = n.data.step.kind
    if (k === 'prompt') { refs.push(`{{steps.${n.id}.output.prompt}}`); refs.push(`{{steps.${n.id}.output.prompts}}`) }
    else if (k === 'gate' || k === 'collect' || k === 'transform') refs.push(`{{steps.${n.id}.output}}`)
    else refs.push(`{{steps.${n.id}.output}}`)
  }
  if (step.kind === 'map') refs.push('{{item}}', '{{index}}')
  return refs
}
