<script setup lang="ts">
// inference.club, the whole thing, in a single breath. A deliberate, tasteful
// gag: one run-on sentence that captures the stack + approach at a glance.
// Kept inline + English on purpose — it's a stylistic easter egg, not body copy.
import { Wind } from 'lucide-vue-next'
</script>

<template>
  <section class="relative px-4 sm:px-6 lg:px-8 py-24 border-t overflow-hidden">
    <!-- soft ambient wash -->
    <div
      class="pointer-events-none absolute inset-0 -z-10 opacity-70"
      style="background: radial-gradient(ellipse at 50% 0%, rgba(34,211,238,0.10), transparent 60%)"
    />
    <div class="max-w-3xl mx-auto">
      <div class="flex items-center justify-center gap-2 mb-8">
        <Wind class="h-4 w-4 text-cyan-500" />
        <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground">In one breath</p>
      </div>

      <blockquote class="relative text-balance text-center text-xl sm:text-2xl md:text-[1.7rem] font-medium leading-relaxed sm:leading-relaxed tracking-tight text-foreground/90">
        <span class="select-none text-4xl align-[-0.3em] mr-1 bg-gradient-to-br from-violet-500 to-fuchsia-500 bg-clip-text text-transparent">“</span>inference.club is what happens when you point an
        <span class="text-foreground font-semibold">OpenAI-compatible API</span> at a pile of consumer GPUs you actually
        <em class="not-italic bg-gradient-to-r from-violet-500 to-fuchsia-500 bg-clip-text text-transparent">own and trust</em> — a private
        <span class="text-foreground font-semibold">Tailscale</span> tailnet quietly stitching a 4090 here, an M3 Ultra there, a DGX Spark and a couple of 3090s into one
        <span class="text-foreground font-semibold">WireGuard</span> mesh with no ports forwarded and no firewall holes, where a little
        <code class="font-mono text-[0.85em] text-foreground">inference-club-agent</code> container sits next to whatever you’re already running —
        <span class="text-foreground">vLLM, llama.cpp, Ollama, LM Studio</span> — and advertises it through a manifest, while back in the cloud a
        <span class="text-foreground font-semibold">Django + Celery</span> server behind Caddy authenticates your
        <code class="font-mono text-[0.85em] text-foreground">ic_</code> key, enforces your
        <em class="not-italic bg-gradient-to-r from-fuchsia-500 to-rose-500 bg-clip-text text-transparent">privacy and per-service access controls</em>, and routes the call over the tailnet by MagicDNS to a healthy online node, with Redis and Postgres driving
        <span class="text-foreground">async jobs, batches and a whole workflow DAG engine</span>, GCS holding the images, video, voice and music that come back, a
        <span class="text-foreground font-semibold">Nuxt playground</span> and dashboard to poke at all of it, the home fleet itself migrating from Docker to
        <span class="text-foreground font-semibold">k3s</span>, and the entire thing — chat, images, LTX-2 video, Dia voice cloning, speech, the works — sitting behind
        <em class="not-italic bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">one base URL you can curl</em>, so go ahead and build something, and, as the prompt says:
        <span class="whitespace-nowrap font-semibold text-foreground">Make no mistakes.</span><span class="select-none text-4xl align-[-0.3em] ml-1 bg-gradient-to-br from-cyan-500 to-violet-500 bg-clip-text text-transparent">”</span>
      </blockquote>
    </div>
  </section>
</template>
