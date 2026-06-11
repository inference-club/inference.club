<!--
  "Tumble" — the perspective jack as a solid silhouette, tilted like a jack
  that just landed from a toss. Same real-toy geometry as Tradesies/Chromies
  but filled and resting at an angle; currentColor, favicon-strong.
-->
<template>
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <g transform="rotate(-20 12 12)">
      <!-- vertical spikes, dull rounded tips -->
      <path d="M10.5 10 L11.4 2.8 Q12 1.95 12.6 2.8 L13.5 10 Z" />
      <path d="M10.5 13.8 L11.4 20.9 Q12 21.75 12.6 20.9 L13.5 13.8 Z" />
      <!-- arms -->
      <g stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
        <line x1="12" y1="11.8" x2="6" y2="16.2" />
        <line x1="12" y1="11.8" x2="18" y2="16.2" />
        <line x1="12" y1="11.8" x2="7.6" y2="7.2" />
        <line x1="12" y1="11.8" x2="16.4" y2="7.2" />
      </g>
      <!-- balls: near pair larger, far pair smaller -->
      <circle cx="5.2" cy="16.8" r="2.4" />
      <circle cx="18.8" cy="16.8" r="2.4" />
      <circle cx="6.9" cy="6.5" r="1.8" />
      <circle cx="17.1" cy="6.5" r="1.8" />
      <!-- hub -->
      <circle cx="12" cy="11.8" r="2.6" />
    </g>
  </svg>
</template>
