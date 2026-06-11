<!--
  "Tradesies" — the real toy in perspective, monoline: vertical spike axis,
  and the four ball arms foreshortened the way a photographed jack reads —
  near pair low, wide, and big; far pair high, narrow, and small. Symmetric
  left/right so it stays balanced as a mark. currentColor.
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
    <!-- vertical spikes -->
    <line x1="12" y1="9.6" x2="12" y2="2.6" />
    <line x1="12" y1="14" x2="12" y2="21" />
    <!-- near arms: longer, bigger balls -->
    <line x1="10.2" y1="13.1" x2="6.5" y2="15.9" />
    <line x1="13.8" y1="13.1" x2="17.5" y2="15.9" />
    <circle cx="4.9" cy="17.1" r="2.05" />
    <circle cx="19.1" cy="17.1" r="2.05" />
    <!-- far arms: shorter, smaller balls -->
    <line x1="10.5" y1="10.2" x2="7.7" y2="7.4" />
    <line x1="13.5" y1="10.2" x2="16.3" y2="7.4" />
    <circle cx="6.7" cy="6.3" r="1.5" />
    <circle cx="17.3" cy="6.3" r="1.5" />
    <!-- hub -->
    <circle cx="12" cy="11.8" r="2.2" fill="currentColor" stroke="none" />
  </svg>
</template>
