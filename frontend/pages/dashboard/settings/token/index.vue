<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  Copy,
} from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const { token, tokens, isLoading, error, createToken, deleteToken, refreshTokens } = useToken()
const showCopied = ref(false)

onMounted(() => {
  refreshTokens()
})

const copyToClipboard = async () => {
  if (token.value) {
    await navigator.clipboard.writeText(token.value)
    showCopied.value = true
    setTimeout(() => {
      showCopied.value = false
    }, 2000)
  }
}

definePageMeta({
  layout: 'app'
})
</script>

<template>
  <div class="container max-w-2xl pt-16 px-4 mx-auto">
    <div class="space-y-10">
      <div class="mb-6">
        <h1 class="text-3xl font-bold mb-2">API Token</h1>
        <p class="text-muted-foreground text-lg">
          Manage your API token for accessing the platform's API.
        </p>
      </div>

      <Card class="p-6">
        <CardHeader>
          <CardTitle>Your API Token</CardTitle>
          <CardDescription>
            Keep this token secure. It provides access to your account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div v-if="error" class="mb-4">
            <Alert variant="destructive">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{{ error }}</AlertDescription>
            </Alert>
          </div>

          <div v-if="token" class="space-y-4">
            <div class="flex items-center gap-2">
              <Input
                v-model="token"
                readonly
                class="font-mono"
              />
              <Popover :open="showCopied">
                <PopoverTrigger as-child>
                  <Button
                    variant="outline"
                    size="icon"
                    @click="copyToClipboard"
                  >
                    <Copy class="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent class="w-auto p-2" side="top" align="center">
                  Copied!
                </PopoverContent>
              </Popover>
            </div>
            <p class="text-sm text-muted-foreground">
              This is the only time you will see your full API token. Please copy and store it securely.
            </p>
            <Button
              variant="destructive"
              :disabled="isLoading"
              @click="deleteToken"
            >
              Delete Token
            </Button>
          </div>
          <div v-else-if="tokens.length > 0" class="space-y-4">
            <div class="flex flex-col gap-2">
              <span
                v-for="t in tokens"
                :key="t.id"
                class="font-mono font-bold text-muted-foreground"
              >
                Token prefix: {{ t.prefix }}
              </span>
            </div>
            <p class="text-sm text-muted-foreground">
              For security, the full token is only shown once when created. If you lost it, delete and create a new token.
            </p>
            <Button
              variant="destructive"
              :disabled="isLoading"
              @click="deleteToken"
            >
              Delete Token
            </Button>
          </div>

          <div v-else class="space-y-4">
            <p class="text-sm text-muted-foreground">
              You don't have an active API token. Create one to get started.
            </p>
            <Button
              :disabled="isLoading"
              @click="createToken"
            >
              <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
              Create Token
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
