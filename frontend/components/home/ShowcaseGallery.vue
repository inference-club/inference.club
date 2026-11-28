<script setup lang="ts">
// "Made here": the club's own work, served as static files so the homepage
// shows the same pieces on every deployment. The list comes from
// public/showcase/index.json, written by scripts/showcase/generate.py; each
// entry carries the model, GPU, time taken and seed that made it.
import { computed } from 'vue'
import { Cpu, Timer, Dices, Quote } from 'lucide-vue-next'
import index from '~/public/showcase/index.json'
import { prettyGpuModel } from '@/composables/useMachineForm'

interface Piece {
  id: string
  kind: 'image' | 'music' | 'video' | 'speech' | 'chat'
  title: string
  model: string
  prompt?: string
  seed?: number | null
  gpu?: string | null
  seconds?: number | null
  length?: number | null
  src?: string
  thumb?: string
  cover?: string
  text?: string
}

const { t } = useI18n()
const lightbox = useImageLightbox()
const url = (f?: string) => (f ? `/showcase/${f}` : '')

const pieces = index.items as Piece[]
// Covers belong to their songs, not to the picture wall.
const pictures = computed(() => pieces.filter((p) => p.kind === 'image' && !p.id.startsWith('cover-')))
const songs = computed(() => pieces.filter((p) => p.kind === 'music'))
const voice = computed(() => pieces.find((p) => p.kind === 'speech'))
const words = computed(() => pieces.find((p) => p.kind === 'chat'))
const hasVideo = computed(() => pieces.some((p) => p.kind === 'video'))
const pictureUrls = computed(() => pictures.value.map((p) => url(p.src)))
</script>

<template>
  <section id="made-here" class="px-4 py-16 sm:px-6 sm:py-24 lg:px-8" data-testid="showcase-gallery">
    <div class="mx-auto max-w-6xl">
      <div class="mb-10 max-w-2xl">
        <p class="mb-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{{ t('landing.gallery.eyebrow') }}</p>
        <h2 class="text-3xl font-bold tracking-tight sm:text-5xl">{{ t('landing.gallery.title') }}</h2>
        <p class="mt-4 text-muted-foreground">{{ t('landing.gallery.subtitle') }}</p>
      </div>

      <!-- Pictures: a masonry wall; every one opens in the lightbox. -->
      <div class="columns-2 gap-3 sm:columns-3 lg:columns-4 [&>figure]:mb-3">
        <figure
          v-for="(p, i) in pictures"
          :key="p.id"
          class="group relative break-inside-avoid overflow-hidden rounded-xl border bg-muted"
        >
          <button
            type="button"
            class="block w-full cursor-zoom-in"
            :aria-label="`${t('landing.gallery.open')}: ${p.title}`"
            @click="lightbox.openList(pictureUrls, i)"
          >
            <img
              :src="url(p.thumb)"
              :alt="p.title"
              loading="lazy"
              decoding="async"
              class="w-full transition duration-500 group-hover:scale-[1.03]"
            />
          </button>
          <figcaption
            class="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent px-3 pb-2.5 pt-8 text-white"
          >
            <p class="truncate text-sm font-medium">{{ p.title }}</p>
            <p class="flex flex-wrap items-center gap-x-2.5 text-[11px] text-white/80">
              <span v-if="p.gpu" class="inline-flex items-center gap-1"><Cpu class="size-3" />{{ prettyGpuModel(p.gpu) }}</span>
              <span v-if="p.seconds" class="inline-flex items-center gap-1"><Timer class="size-3" />{{ t('landing.gallery.seconds', { n: p.seconds }) }}</span>
              <span v-if="p.seed != null" class="hidden items-center gap-1 sm:inline-flex"><Dices class="size-3" />{{ p.seed }}</span>
            </p>
          </figcaption>
        </figure>
      </div>

      <!-- Songs -->
      <h3 class="mb-4 mt-14 text-lg font-semibold">{{ t('landing.gallery.songs') }}</h3>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <article
          v-for="s in songs"
          :key="s.id"
          class="flex min-w-0 flex-col gap-3 rounded-2xl border bg-card p-3"
        >
          <div class="flex min-w-0 items-center gap-3">
            <button
              v-if="s.cover"
              type="button"
              class="shrink-0 cursor-zoom-in"
              :aria-label="`${t('landing.gallery.open')}: ${s.title}`"
              @click="lightbox.open(url(s.cover))"
            >
              <img :src="url(s.cover.replace('.webp', '-sm.webp'))" :alt="s.title" loading="lazy" class="size-20 rounded-xl border object-cover" />
            </button>
            <div class="min-w-0">
              <p class="truncate font-semibold">{{ s.title }}</p>
              <p class="truncate text-xs text-muted-foreground">{{ s.model }}</p>
              <p class="mt-1 flex flex-wrap items-center gap-x-2.5 text-[11px] text-muted-foreground">
                <span v-if="s.gpu" class="inline-flex items-center gap-1"><Cpu class="size-3" />{{ prettyGpuModel(s.gpu) }}</span>
                <span v-if="s.seconds" class="inline-flex items-center gap-1"><Timer class="size-3" />{{ t('landing.gallery.seconds', { n: s.seconds }) }}</span>
                <span v-if="s.seed != null" class="inline-flex items-center gap-1"><Dices class="size-3" />{{ s.seed }}</span>
              </p>
            </div>
          </div>
          <AudioClip :src="url(s.src)" :seconds="s.length" />
        </article>
      </div>

      <!-- A voice and some words -->
      <div class="mt-6 grid gap-4 lg:grid-cols-2">
        <article v-if="voice" class="min-w-0 rounded-2xl border bg-card p-4">
          <h3 class="mb-1 text-sm font-semibold">{{ t('landing.gallery.voice') }}</h3>
          <p class="mb-3 text-sm text-muted-foreground">“{{ voice.prompt }}”</p>
          <AudioClip :src="url(voice.src)" :seconds="voice.length" />
          <p class="mt-2 flex flex-wrap items-center gap-x-2.5 text-[11px] text-muted-foreground">
            <span>{{ voice.model }}</span>
            <span v-if="voice.gpu" class="inline-flex items-center gap-1"><Cpu class="size-3" />{{ prettyGpuModel(voice.gpu) }}</span>
            <span v-if="voice.seconds" class="inline-flex items-center gap-1"><Timer class="size-3" />{{ t('landing.gallery.seconds', { n: voice.seconds }) }}</span>
          </p>
        </article>
        <article v-if="words" class="min-w-0 rounded-2xl border bg-card p-4">
          <h3 class="mb-1 text-sm font-semibold">{{ t('landing.gallery.words') }}</h3>
          <p class="mb-3 text-sm text-muted-foreground">“{{ words.prompt }}”</p>
          <blockquote class="relative whitespace-pre-line rounded-xl bg-muted/50 p-4 pl-10 text-sm leading-relaxed">
            <Quote class="absolute left-3 top-4 size-4 text-muted-foreground" />{{ words.text }}
          </blockquote>
          <p class="mt-2 flex flex-wrap items-center gap-x-2.5 text-[11px] text-muted-foreground">
            <span class="truncate">{{ words.model }}</span>
            <span v-if="words.gpu" class="inline-flex items-center gap-1"><Cpu class="size-3" />{{ prettyGpuModel(words.gpu) }}</span>
            <span v-if="words.seconds" class="inline-flex items-center gap-1"><Timer class="size-3" />{{ t('landing.gallery.seconds', { n: words.seconds }) }}</span>
          </p>
        </article>
      </div>

      <p v-if="!hasVideo" class="mt-6 text-sm text-muted-foreground">{{ t('landing.gallery.videoNote') }}</p>
    </div>
  </section>
</template>
