<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, RefreshCw } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useToken } from '@/composables/useToken'
import { useAuth } from '@/composables/useAuth'

const { token, isLoading, error, createToken } = useToken()
const { user, checkAuth } = useAuth()
const config = useRuntimeConfig()
const showCopied = ref(false)

// The key is auto-minted on signup and returned on /api/account/. After a
// regenerate, the composable holds the fresh value; otherwise fall back to the
// one carried on the user object.
const apiKey = computed(() => token.value || user.value?.api_token || '')

const copyToClipboard = async () => {
  if (!apiKey.value) return
  await navigator.clipboard.writeText(apiKey.value)
  showCopied.value = true
  setTimeout(() => { showCopied.value = false }, 2000)
}

const regenerate = async () => {
  if (!confirm('Regenerate your API key? Your current key will stop working immediately.')) return
  await createToken()
  // Sync the store so user.api_token reflects the new key everywhere.
  await checkAuth()
}

definePageMeta({
  layout: 'app',
})
</script>

<template>
  <div class="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6">
    <div class="space-y-10">
      <div class="mb-6">
        <h1 class="text-3xl font-bold mb-2">API Token</h1>
        <p class="text-muted-foreground text-lg">
          Use this key with any OpenAI-compatible client to reach inference.club.
        </p>
      </div>

      <Card class="p-6">
        <CardHeader>
          <CardTitle>Your API Token</CardTitle>
          <CardDescription>
            Keep this token secret — it grants full access to your account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div v-if="error" class="mb-4">
            <Alert variant="destructive">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{{ error }}</AlertDescription>
            </Alert>
          </div>

          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <Input :model-value="apiKey" readonly class="font-mono" />
              <Popover :open="showCopied">
                <PopoverTrigger as-child>
                  <Button variant="outline" size="icon" @click="copyToClipboard">
                    <Copy class="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent class="w-auto p-2" side="top" align="center">
                  Copied!
                </PopoverContent>
              </Popover>
            </div>
            <p class="text-sm text-muted-foreground">
              Set it as the API key / bearer token in your client, with base URL
              <code class="font-mono text-foreground">{{ config.public.apiBase }}/v1</code>.
            </p>
            <Button variant="outline" :disabled="isLoading" @click="regenerate">
              <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': isLoading }" />
              {{ isLoading ? 'Regenerating…' : 'Regenerate token' }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
