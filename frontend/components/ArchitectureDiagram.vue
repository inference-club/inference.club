<script setup lang="ts">
// A detailed, conceptual networking + architecture diagram for the home page.
// Deliberately not 3D — this is the "read the whole pipeline at a glance" view:
// how a request flows from your code, through the cloud control plane, across
// the private Tailscale tailnet, into the agent container, and down to the
// local LLM server on someone's consumer GPU. Labels are intentionally
// technical (they're proper nouns / code), so they're left untranslated.
import {
  Terminal,
  KeyRound,
  ShieldCheck,
  Network,
  Boxes,
  Cpu,
  ArrowDown,
  Lock,
  Server,
  Database,
  Workflow,
  HardDrive,
} from 'lucide-vue-next'

// The cloud control-plane building blocks (Hetzner VPS).
const cloudParts = [
  { icon: Lock, label: 'Caddy', note: 'TLS · reverse proxy' },
  { icon: Server, label: 'Django + DRF', note: 'OpenAI-compatible /v1 router · auth · routing' },
  { icon: ShieldCheck, label: 'Access control', note: 'visibility · per-service ACLs · kill switch' },
  { icon: Workflow, label: 'Celery workers', note: 'async jobs · batches · workflow DAG' },
  { icon: Database, label: 'Postgres + Redis', note: 'state · queue · throttling' },
  { icon: HardDrive, label: 'GCS', note: 'images · video · voice · music' },
]

// What the agent forwards to, on the operator's own machine.
const localEngines = ['vLLM', 'llama.cpp', 'Ollama', 'LM Studio', 'Dia', 'LTX-2']
const rigs = ["brian's 4090", 'M3 Ultra · 192GB', 'DGX Spark', '2× 3090 rig']

// The end-to-end lifecycle, spelled out underneath the picture.
const lifecycle = [
  'Your code calls api.inference.club/v1 with your ic_ key — the same request you’d send OpenAI.',
  'Caddy terminates TLS; Django authenticates the key and applies your privacy + access rules.',
  'The router picks a healthy, online node that actually serves the requested model.',
  'Django (via a Tailscale SOCKS5 sidecar) dials the node by MagicDNS over WireGuard — no ports, no tunnels.',
  'The agent container hands the request to your local LLM server on localhost.',
  'Tokens (or images / video / audio) stream back along the exact same path.',
]
</script>

<template>
  <div class="relative">
    <!-- ============ THE PIPELINE ============ -->
    <div class="mx-auto max-w-3xl space-y-3">
      <!-- Zone 1: your application -->
      <div class="rounded-2xl border bg-card p-5 sm:p-6 shadow-sm">
        <div class="flex items-center gap-3 mb-4">
          <div class="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
            <Terminal class="h-[18px] w-[18px] text-white" />
          </div>
          <div class="min-w-0">
            <p class="font-semibold leading-tight">Your application</p>
            <p class="text-xs text-muted-foreground">curl · OpenAI SDK · the Playground · your agents</p>
          </div>
          <span class="ml-auto hidden sm:inline-block text-[10px] font-mono uppercase tracking-wider text-muted-foreground">client</span>
        </div>
        <div class="rounded-lg bg-muted/60 border border-border/60 p-3 font-mono text-[11px] sm:text-xs leading-relaxed overflow-x-auto">
          <span class="text-muted-foreground">base_url</span> = <span class="text-fuchsia-500">"https://api.inference.club/v1"</span><br>
          <span class="text-muted-foreground">api_key</span>  = <span class="text-violet-500">"ic_xxxxxxxxxxxxxxxxxxxx"</span>
        </div>
      </div>

      <!-- Connector 1 -->
      <div class="flex items-center justify-center gap-3 py-1">
        <div class="h-px w-10 bg-gradient-to-r from-transparent to-violet-500/40" />
        <span class="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-[11px] font-mono text-muted-foreground">
          <KeyRound class="h-3.5 w-3.5 text-violet-500" />
          HTTPS · Authorization: Bearer ic_…
        </span>
        <div class="h-px w-10 bg-gradient-to-l from-transparent to-violet-500/40" />
      </div>
      <div class="flex justify-center -my-1"><ArrowDown class="h-4 w-4 text-muted-foreground/60" /></div>

      <!-- Zone 2: the cloud control plane -->
      <div class="relative rounded-2xl border border-fuchsia-500/30 bg-gradient-to-b from-fuchsia-500/[0.04] to-transparent p-5 sm:p-6 shadow-sm">
        <div class="flex items-center gap-3 mb-4">
          <div class="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-fuchsia-500 to-rose-500 flex items-center justify-center">
            <Boxes class="h-[18px] w-[18px] text-white" />
          </div>
          <div class="min-w-0">
            <p class="font-semibold leading-tight">api.inference.club <span class="text-muted-foreground font-normal">— the control plane</span></p>
            <p class="text-xs text-muted-foreground">one small cloud VPS (Hetzner). It routes; it never runs the model.</p>
          </div>
          <span class="ml-auto hidden sm:inline-block text-[10px] font-mono uppercase tracking-wider text-muted-foreground">cloud</span>
        </div>
        <div class="grid sm:grid-cols-2 gap-2">
          <div
            v-for="p in cloudParts"
            :key="p.label"
            class="flex items-start gap-2.5 rounded-lg border bg-card/70 px-3 py-2.5"
          >
            <component :is="p.icon" class="h-4 w-4 mt-0.5 shrink-0 text-fuchsia-500" />
            <div class="min-w-0">
              <p class="text-sm font-medium leading-tight">{{ p.label }}</p>
              <p class="text-[11px] text-muted-foreground leading-snug">{{ p.note }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Connector 2: the tailnet — the heart of the whole thing -->
      <div class="flex justify-center -mb-1 mt-1"><ArrowDown class="h-4 w-4 text-muted-foreground/60" /></div>
      <div class="relative rounded-2xl border border-cyan-500/40 bg-cyan-500/[0.05] px-5 py-4 overflow-hidden">
        <div
class="pointer-events-none absolute inset-0 opacity-[0.18] dark:opacity-[0.25]"
             :style="{ backgroundImage: 'radial-gradient(circle at 1px 1px, rgb(34 211 238) 1px, transparent 0)', backgroundSize: '20px 20px' }" />
        <div class="relative flex flex-col sm:flex-row sm:items-center gap-3">
          <div class="flex items-center gap-3">
            <div class="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
              <Network class="h-[18px] w-[18px] text-white" />
            </div>
            <div>
              <p class="font-semibold leading-tight">The inference.club tailnet</p>
              <p class="text-xs text-muted-foreground">a private Tailscale mesh — pure WireGuard</p>
            </div>
          </div>
          <div class="sm:ml-auto flex flex-wrap gap-1.5 font-mono text-[10px]">
            <span class="rounded-full border border-cyan-500/40 bg-background/60 px-2 py-0.5">SOCKS5 sidecar</span>
            <span class="rounded-full border border-cyan-500/40 bg-background/60 px-2 py-0.5">MagicDNS · club-host-17:443</span>
            <span class="rounded-full border border-cyan-500/40 bg-background/60 px-2 py-0.5">short-lived auth keys</span>
            <span class="rounded-full border border-cyan-500/40 bg-background/60 px-2 py-0.5">no ports · no firewall holes</span>
          </div>
        </div>
      </div>
      <div class="flex justify-center -mt-1"><ArrowDown class="h-4 w-4 text-muted-foreground/60" /></div>

      <!-- Zone 3: the rig -->
      <div class="rounded-2xl border bg-card p-5 sm:p-6 shadow-sm">
        <div class="flex items-center gap-3 mb-4">
          <div class="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center">
            <Cpu class="h-[18px] w-[18px] text-white" />
          </div>
          <div class="min-w-0">
            <p class="font-semibold leading-tight">Your rig <span class="text-muted-foreground font-normal">— where inference actually happens</span></p>
            <p class="text-xs text-muted-foreground">a GPU you own, at home, on hardware you trust</p>
          </div>
          <span class="ml-auto hidden sm:inline-block text-[10px] font-mono uppercase tracking-wider text-muted-foreground">operator</span>
        </div>

        <!-- the agent container -->
        <div class="rounded-xl border border-dashed border-emerald-500/50 bg-emerald-500/[0.04] p-3 sm:p-4">
          <div class="flex items-center gap-2 mb-3">
            <Boxes class="h-4 w-4 text-emerald-500" />
            <code class="text-xs font-mono">inference-club-agent</code>
            <span class="text-[10px] font-mono text-muted-foreground">container · --network host</span>
          </div>
          <p class="text-[11px] text-muted-foreground leading-snug mb-3">
            Joins the tailnet with its minted key, advertises models from
            <code class="font-mono text-foreground">agent.yaml</code>, and forwards each request to whatever you already run locally:
          </p>
          <div class="flex flex-wrap gap-1.5 mb-1">
            <span
              v-for="e in localEngines"
              :key="e"
              class="rounded-md border bg-background px-2 py-1 font-mono text-[11px]"
            >{{ e }}</span>
          </div>
          <p class="mt-3 text-[11px] font-mono text-muted-foreground">→ http://localhost:1234/v1</p>
        </div>

        <!-- the hardware -->
        <div class="mt-3 flex flex-wrap items-center gap-1.5">
          <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">running on</span>
          <span
            v-for="r in rigs"
            :key="r"
            class="rounded-full border border-emerald-500/30 bg-emerald-500/[0.06] px-2.5 py-0.5 text-[11px] font-mono"
          >{{ r }}</span>
          <span class="rounded-full border bg-muted px-2.5 py-0.5 text-[11px] font-mono text-muted-foreground">k3s home cluster</span>
        </div>
      </div>
    </div>

    <!-- ============ FOLLOW A REQUEST ============ -->
    <div class="mx-auto max-w-3xl mt-10">
      <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-4 text-center">Follow one request</p>
      <ol class="grid sm:grid-cols-2 gap-x-6 gap-y-3">
        <li v-for="(step, i) in lifecycle" :key="i" class="flex gap-3">
          <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 text-[10px] font-mono font-semibold text-white">
            {{ i + 1 }}
          </span>
          <span class="text-sm text-muted-foreground leading-snug">{{ step }}</span>
        </li>
      </ol>
    </div>
  </div>
</template>
