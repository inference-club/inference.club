<script setup lang="ts">
import InferenceRequestForm from '@/components/InferenceRequestForm.vue'

definePageMeta({
  layout: 'app',
})

</script>

<template>
  <div class="container mx-auto py-6">
    <div class="max-w-2xl mx-auto">
      <h1 class="text-2xl font-bold mb-6">Create Inference Request</h1>
      <InferenceRequestForm />
    </div>
  </div>
</template>