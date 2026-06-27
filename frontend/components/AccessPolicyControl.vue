<script setup lang="ts">
import { computed } from 'vue'
import { Lock, Globe, Users } from 'lucide-vue-next'
import type { AccessPolicy } from '@/composables/useServices'

// One reusable access-policy editor — a policy select + Save, plus a GitHub
// allowlist when RESTRICTED. Shared verbatim by all three gating levels
// (cluster, node, service) so the markup lives in exactly one place.
const props = defineProps<{
  policy: AccessPolicy
  allowlist: string[]
  label?: string
  saving?: boolean
  saveVariant?: 'default' | 'outline'
  hint?: string
}>()

const emit = defineEmits<{
  'update:policy': [AccessPolicy]
  'update:allowlist': [string[]]
  save: []
}>()

const LABELS: Record<AccessPolicy, string> = {
  PRIVATE: 'Only me',
  AUTHENTICATED: 'Any inference.club member',
  RESTRICTED: 'Specific GitHub users',
}

const policyModel = computed({
  get: () => props.policy,
  set: (v: AccessPolicy) => emit('update:policy', v),
})
const allowlistModel = computed({
  get: () => props.allowlist,
  set: (v: string[]) => emit('update:allowlist', v),
})
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-center gap-2">
      <label v-if="label" class="text-xs font-medium text-muted-foreground w-28 shrink-0">{{ label }}</label>
      <Select v-model="policyModel">
        <SelectTrigger class="h-8 text-sm w-full sm:w-64">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="PRIVATE">
            <span class="inline-flex items-center gap-2"><Lock class="size-3.5" /> {{ LABELS.PRIVATE }}</span>
          </SelectItem>
          <SelectItem value="AUTHENTICATED">
            <span class="inline-flex items-center gap-2"><Globe class="size-3.5" /> {{ LABELS.AUTHENTICATED }}</span>
          </SelectItem>
          <SelectItem value="RESTRICTED">
            <span class="inline-flex items-center gap-2"><Users class="size-3.5" /> {{ LABELS.RESTRICTED }}</span>
          </SelectItem>
        </SelectContent>
      </Select>
      <Button
        size="sm"
        :variant="saveVariant || 'default'"
        class="h-8 ml-auto"
        :disabled="saving"
        @click="emit('save')"
      >
        {{ saving ? 'Saving…' : 'Save' }}
      </Button>
    </div>

    <div v-if="policy === 'RESTRICTED'" :class="label ? 'flex flex-wrap items-start gap-2' : ''">
      <label v-if="label" class="text-xs font-medium text-muted-foreground w-28 shrink-0 pt-2">Allowed users</label>
      <div class="flex-1 min-w-0">
        <TagsInput v-model="allowlistModel" class="w-full">
          <TagsInputItem v-for="u in allowlist" :key="u" :value="u">
            <TagsInputItemText />
            <TagsInputItemDelete />
          </TagsInputItem>
          <TagsInputInput placeholder="github-username, then Enter" />
        </TagsInput>
        <p class="text-xs text-muted-foreground mt-1">
          Type a GitHub username and press Enter. Case-insensitive.
        </p>
      </div>
    </div>

    <p
      v-if="hint && policy !== 'AUTHENTICATED'"
      class="text-xs text-muted-foreground"
      :class="label ? 'sm:pl-30' : ''"
    >
      {{ hint }}
    </p>
  </div>
</template>
