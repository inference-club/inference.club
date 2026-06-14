<script setup lang="ts">
/**
 * Workflow DAG on a real node canvas (Vue Flow): pan, zoom, fit-view, minimap,
 * and rich custom nodes. Layout is computed with dagre (left→right by
 * dependency depth) and refreshed as the run is polled — node positions are
 * stable, so the viewport (your pan/zoom) is preserved across updates.
 */
import { computed, markRaw, ref } from 'vue'
import { VueFlow, useVueFlow, MarkerType, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import dagre from '@dagrejs/dagre'
import WorkflowNode from './WorkflowNode.vue'
import { modalityHex } from '@/composables/useClusterState'
import type { WorkflowRun } from '@/composables/useAsyncJobs'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const props = defineProps<{ run: WorkflowRun }>()
const emit = defineEmits<{ (e: 'gate', p: { stepId: string; action: 'approve' | 'reject' }): void }>()

const nodeTypes = { workflow: markRaw(WorkflowNode) }
const onGate = (stepId: string, action: 'approve' | 'reject') => emit('gate', { stepId, action })

const NODE_W = 248
const NODE_H = 200

const graph = computed(() => {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 90, marginx: 24, marginy: 24 })
  for (const s of props.run.steps) g.setNode(s.step_id, { width: NODE_W, height: NODE_H })
  const valid = new Set(props.run.steps.map((s) => s.step_id))
  for (const e of props.run.edges) {
    if (valid.has(e.from) && valid.has(e.to)) g.setEdge(e.from, e.to)
  }
  dagre.layout(g)

  const statusOf: Record<string, string> = {}
  props.run.steps.forEach((s) => { statusOf[s.step_id] = s.status })

  const nodes = props.run.steps.map((s) => {
    const n = g.node(s.step_id)
    return {
      id: s.step_id,
      type: 'workflow',
      position: { x: n.x - NODE_W / 2, y: n.y - NODE_H / 2 },
      data: { step: s, onGate },
    }
  })
  const edges = props.run.edges
    .filter((e) => valid.has(e.from) && valid.has(e.to))
    .map((e) => ({
      id: `${e.from}->${e.to}`,
      source: e.from,
      target: e.to,
      animated: statusOf[e.to] === 'RUNNING',
      markerEnd: MarkerType.ArrowClosed,
      style: { strokeWidth: 1.5 },
    }))
  return { nodes, edges }
})

const { fitView } = useVueFlow()
const fitted = ref(false)
const onInit = () => {
  if (fitted.value) return
  fitted.value = true
  setTimeout(() => fitView({ padding: 0.2 }), 50)
}
</script>

<template>
  <div class="h-[70vh] min-h-[420px] overflow-hidden rounded-lg border bg-muted/20">
    <VueFlow
      :nodes="graph.nodes"
      :edges="graph.edges"
      :node-types="nodeTypes"
      :min-zoom="0.2"
      :max-zoom="2"
      :default-edge-options="{ type: 'smoothstep' }"
      fit-view-on-init
      @nodes-initialized="onInit"
    >
      <Background :gap="20" pattern-color="#94a3b833" />
      <Controls />
      <MiniMap
        pannable zoomable
        :node-color="(n) => modalityHex(((run.steps.find((s) => s.step_id === n.id)?.jobs?.[0]?.inference_type) || '').toLowerCase())"
      />
    </VueFlow>
  </div>
</template>

<style scoped>
/* Let Vue Flow theme variables follow our dark/light surfaces. */
:deep(.vue-flow__minimap) {
  background-color: hsl(var(--background));
}
</style>
