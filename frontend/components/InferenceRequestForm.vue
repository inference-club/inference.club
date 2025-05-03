<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import type { InferenceRequest, InferenceType } from '@/types'

const router = useRouter()
const store = useInferenceRequestStore()

const inferenceTypes: { value: InferenceType; label: string }[] = [
  { value: 'LLM', label: 'Language Model' },
  { value: 'IMAGE', label: 'Image Generation' },
  { value: 'VIDEO', label: 'Video Generation' },
  { value: 'TTS', label: 'Text to Speech' },
]

interface FormPayload {
  prompt: string
}

const form = ref<{
  inference_type: InferenceType
  payload: FormPayload
}>({
  inference_type: 'LLM',
  payload: {
    prompt: '',
  },
})

const onSubmit = async () => {
  try {
    await store.createRequest(form.value)
    router.push('/dashboard/inference/requests')
  } catch {
    // Error is handled by the store
  }
}
</script>

<template>
  <form class="space-y-6" @submit.prevent="onSubmit">
    <div class="space-y-4">
      <div class="space-y-2">
        <Label for="inference_type">Type</Label>
        <Select v-model="form.inference_type">
          <SelectTrigger>
            <SelectValue placeholder="Select inference type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="type in inferenceTypes"
              :key="type.value"
              :value="type.value"
            >
              {{ type.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-2">
        <Label for="prompt">Prompt</Label>
        <Textarea
          id="prompt"
          v-model="form.payload.prompt"
          placeholder="Enter your prompt"
          required
          class="min-h-[100px]"
        />
      </div>
    </div>

    <Button type="submit" :disabled="store.loading">
      {{ store.loading ? 'Creating...' : 'Create Request' }}
    </Button>
  </form>
</template>