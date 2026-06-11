<!--
  "Sixer" — a dimensional jack drawn in isometric perspective using only
  currentColor: the two crossing ball-tipped arms fade with depth (opacity
  layers) while the vertical spike and center sphere sit in front. Suggests
  the 3D toy without needing a second color.
-->
<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
    <g opacity="0.4">
      <line x1="6" y1="15.5" x2="18" y2="8.5" stroke-width="2.6" stroke-linecap="round" />
      <circle cx="4.6" cy="16.3" r="2.1" fill="currentColor" stroke="none" />
      <circle cx="19.4" cy="7.7" r="2.1" fill="currentColor" stroke="none" />
    </g>
    <g opacity="0.7">
      <line x1="6" y1="8.5" x2="18" y2="15.5" stroke-width="2.6" stroke-linecap="round" />
      <circle cx="4.6" cy="7.7" r="2.1" fill="currentColor" stroke="none" />
      <circle cx="19.4" cy="16.3" r="2.1" fill="currentColor" stroke="none" />
    </g>
    <line x1="12" y1="2.6" x2="12" y2="21.4" stroke-width="2.4" stroke-linecap="round" />
    <circle cx="12" cy="12" r="3.1" fill="currentColor" stroke="none" />
  </svg>
</template>
