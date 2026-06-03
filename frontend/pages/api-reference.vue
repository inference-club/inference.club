<script setup lang="ts">
// The API reference now lives inside the dashboard so it shares the sidebar
// shell with the rest of the authenticated surface. Keep this route as a
// permanent redirect so existing links/bookmarks don't 404.
definePageMeta({ redirect: '/dashboard/api-reference' })
</script>

<template>
  <div />
</template>
