<script setup lang="ts">
// Self-contained system diagram for the architecture docs. No props — it draws
// the canonical inference.club topology: consumers → Hetzner control plane →
// (Tailscale bridge) → home k3s GPU cluster, with media offloaded to GCS.
// Built from layout primitives so it reads cleanly in light/dark and on mobile,
// instead of an ASCII code block.
import { Globe, Server, Lock, Cpu, HardDrive, ArrowDown } from 'lucide-vue-next'

const cluster = ['vLLM', 'LM Studio', 'Flux.2', 'LTX-2', 'Dia', 'ACE-Step', 'Magpie TTS', 'Nemotron ASR', 'TRELLIS']
</script>

<template>
  <div class="not-prose my-7 rounded-2xl border bg-muted/30 p-4 sm:p-6">
    <!-- Consumers -->
    <div class="mx-auto max-w-md rounded-xl border bg-card px-4 py-3 text-center">
      <div class="flex items-center justify-center gap-2 text-sm font-medium">
        <Globe class="size-4 text-muted-foreground" /> Consumers
      </div>
      <p class="mt-0.5 text-xs text-muted-foreground">OpenAI SDKs · curl · browser · agents</p>
    </div>

    <div class="flex justify-center py-1.5 text-muted-foreground/60">
      <span class="flex items-center gap-1.5 text-2xs"><ArrowDown class="size-3.5" /> HTTPS</span>
    </div>

    <!-- Hetzner control plane -->
    <div class="rounded-xl border border-sky-500/30 bg-sky-500/[0.05] p-3 sm:p-4">
      <div class="mb-2.5 flex items-center gap-2 text-2xs font-semibold uppercase tracking-wide text-sky-600 dark:text-sky-400">
        <Server class="size-3.5" /> Hetzner VPS · control plane
      </div>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Caddy<span class="block text-2xs font-normal text-muted-foreground">TLS · SSE</span></div>
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Nuxt<span class="block text-2xs font-normal text-muted-foreground">frontend</span></div>
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Django<span class="block text-2xs font-normal text-muted-foreground">API · routing</span></div>
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Celery<span class="block text-2xs font-normal text-muted-foreground">async jobs</span></div>
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Postgres<span class="block text-2xs font-normal text-muted-foreground">source of truth</span></div>
        <div class="rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Redis<span class="block text-2xs font-normal text-muted-foreground">cache · broker</span></div>
        <div class="col-span-2 rounded-lg border bg-card px-3 py-2 text-center text-xs font-medium">Tailscale sidecar<span class="block text-2xs font-normal text-muted-foreground">SOCKS5 · WireGuard out</span></div>
      </div>
    </div>

    <div class="flex justify-center py-1.5 text-muted-foreground/60">
      <span class="flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5 text-2xs">
        <Lock class="size-3" /> Tailscale tailnet · MagicDNS · no port-forward
      </span>
    </div>

    <!-- Home k3s cluster -->
    <div class="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.05] p-3 sm:p-4">
      <div class="mb-2.5 flex items-center gap-2 text-2xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
        <Cpu class="size-3.5" /> Home k3s cluster · GPU compute
      </div>
      <p class="mb-2 text-xs text-muted-foreground">inference-club-agent (kubernetes discovery) routes <code class="rounded bg-background/70 px-1 text-[0.85em]">/v1/*</code> to in-cluster services across 3× RTX&nbsp;4090 + DGX&nbsp;Spark</p>
      <div class="flex flex-wrap gap-1.5">
        <span v-for="s in cluster" :key="s" class="rounded-md border bg-card px-2 py-1 text-2xs font-medium">{{ s }}</span>
      </div>
    </div>

    <!-- GCS offload -->
    <div class="mt-3 flex items-center gap-2 rounded-xl border border-violet-500/30 bg-violet-500/[0.05] px-4 py-2.5 text-xs">
      <HardDrive class="size-4 shrink-0 text-violet-600 dark:text-violet-400" />
      <span class="text-muted-foreground"><span class="font-medium text-foreground">Generated media</span> (images · audio · video · 3D) is written to Google Cloud Storage and served straight from Google's edge — off the VPS hot path.</span>
    </div>
  </div>
</template>
