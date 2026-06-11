<!--
  "Chromies" — the perspective jack rendered as polished chrome: steel
  gradients on the arms, radial highlights on the balls, tapered mirror
  spikes. Self-colored (ignores currentColor), so it looks the same on any
  background — closest 2D match to the shiny metal toy and the 3D model.
-->
<template>
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="icjack-rod" x1="0" y1="0" x2="0.9" y2="1">
        <stop offset="0" stop-color="#e2e8f0" />
        <stop offset="0.5" stop-color="#8a94a8" />
        <stop offset="1" stop-color="#3f4756" />
      </linearGradient>
      <radialGradient id="icjack-ball" cx="0.33" cy="0.28" r="0.9">
        <stop offset="0" stop-color="#ffffff" />
        <stop offset="0.38" stop-color="#aab3c4" />
        <stop offset="1" stop-color="#46505f" />
      </radialGradient>
      <linearGradient id="icjack-spike" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#d8dee8" />
        <stop offset="0.55" stop-color="#7a8498" />
        <stop offset="1" stop-color="#39404e" />
      </linearGradient>
    </defs>
    <!-- vertical spikes, dull rounded tips -->
    <path d="M10.5 10 L11.4 2.6 Q12 1.7 12.6 2.6 L13.5 10 Z" fill="url(#icjack-spike)" />
    <path d="M10.5 13.8 L11.4 21.2 Q12 22.1 12.6 21.2 L13.5 13.8 Z" fill="url(#icjack-spike)" />
    <!-- arms -->
    <g stroke="url(#icjack-rod)" stroke-width="2.4" stroke-linecap="round">
      <line x1="12" y1="11.8" x2="5.8" y2="16.4" />
      <line x1="12" y1="11.8" x2="18.2" y2="16.4" />
      <line x1="12" y1="11.8" x2="7.5" y2="7.1" />
      <line x1="12" y1="11.8" x2="16.5" y2="7.1" />
    </g>
    <!-- balls: near pair larger, far pair smaller -->
    <circle cx="4.9" cy="17.1" r="2.5" fill="url(#icjack-ball)" />
    <circle cx="19.1" cy="17.1" r="2.5" fill="url(#icjack-ball)" />
    <circle cx="6.7" cy="6.3" r="1.85" fill="url(#icjack-ball)" />
    <circle cx="17.3" cy="6.3" r="1.85" fill="url(#icjack-ball)" />
    <!-- hub -->
    <circle cx="12" cy="11.8" r="2.6" fill="url(#icjack-ball)" />
  </svg>
</template>
