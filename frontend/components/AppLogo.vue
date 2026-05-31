<!--
  inference.club mark — a small mesh of inference nodes routing into a
  central hub. Uses currentColor so it adapts to light/dark and inherits
  sizing via class fallthrough (e.g. <Logo class="size-5" />).
-->
<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <line x1="6.4" y1="6.4" x2="10.3" y2="10.3" />
    <line x1="17.6" y1="6.4" x2="13.7" y2="10.3" />
    <line x1="6.4" y1="17.6" x2="10.3" y2="13.7" />
    <line x1="17.6" y1="17.6" x2="13.7" y2="13.7" />
    <circle cx="5" cy="5" r="1.9" />
    <circle cx="19" cy="5" r="1.9" />
    <circle cx="5" cy="19" r="1.9" />
    <circle cx="19" cy="19" r="1.9" />
    <circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none" />
  </svg>
</template>
