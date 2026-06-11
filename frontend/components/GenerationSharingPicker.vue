<script setup lang="ts">
// Global visibility + collection picker that sits next to every playground's
// Generate button. It edits the *account defaults* (default_request_visibility
// and default_collection_name) — the backend applies them to each new
// generation — so the choice persists and is shared by all playgrounds.
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  Globe,
  Link2,
  Users,
  Lock,
  Check,
  ChevronDown,
  FolderOpen,
  Loader2,
} from 'lucide-vue-next'
import type { Collection, Visibility } from '@/types'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'
import { useContentSharing } from '@/composables/useContentSharing'

// compact: icon-only trigger for tight rows (the chat composer).
const props = defineProps<{ compact?: boolean }>()

const { t } = useI18n()
const { user, updateAccount } = useAuth()
const { listCollections } = useContentSharing()

const ICONS: Record<Visibility, typeof Globe> = {
  PUBLIC: Globe,
  UNLISTED: Link2,
  PRIVATE: Users,
  SECRET: Lock,
}

const open = ref(false)
const saving = ref(false)
const collections = ref<Collection[]>([])
const collectionsLoaded = ref(false)
const loadingCollections = ref(false)
const newName = ref('')

const visibility = computed<Visibility>(
  () => user.value?.default_request_visibility ?? 'UNLISTED',
)
const collectionName = computed(() => user.value?.default_collection_name ?? '')

const loadCollections = async () => {
  if (collectionsLoaded.value || loadingCollections.value) return
  loadingCollections.value = true
  try {
    collections.value = await listCollections()
    collectionsLoaded.value = true
  } catch {
    toast.error(t('sharing.loadCollectionsFailed'))
  } finally {
    loadingCollections.value = false
  }
}

const onOpenChange = (v: boolean) => {
  open.value = v
  if (v) loadCollections()
}

const setVisibility = async (v: Visibility) => {
  if (v === visibility.value || saving.value) return
  saving.value = true
  try {
    await updateAccount({ default_request_visibility: v })
  } catch {
    toast.error(t('sharing.updateFailed'))
  } finally {
    saving.value = false
  }
}

const setCollection = async (name: string) => {
  if (name === collectionName.value || saving.value) return
  saving.value = true
  try {
    await updateAccount({ default_collection_name: name })
  } catch {
    toast.error(t('sharing.updateFailed'))
  } finally {
    saving.value = false
  }
}

// Picking a brand-new name just saves it as the default — the backend
// creates the collection on the first generation that uses it.
const createAndSelect = async () => {
  const name = newName.value.trim()
  if (!name) return
  await setCollection(name)
  if (!collections.value.some((c) => c.name.toLowerCase() === name.toLowerCase())) {
    collections.value.unshift({ name } as Collection)
  }
  newName.value = ''
}

const isSelectedCollection = (name: string) =>
  name.toLowerCase() === collectionName.value.toLowerCase()
</script>

<template>
  <Popover :open="open" @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button
        v-if="props.compact"
        variant="ghost"
        size="icon"
        class="rounded-full size-9 text-muted-foreground"
        :title="`${VISIBILITY_META[visibility].short}${collectionName ? ' · ' + collectionName : ''}`"
        :aria-label="t('sharing.triggerLabel')"
      >
        <component :is="ICONS[visibility]" class="size-5" />
      </Button>
      <Button
        v-else
        variant="outline"
        class="gap-1.5 max-w-56"
        :aria-label="t('sharing.triggerLabel')"
      >
        <component :is="ICONS[visibility]" class="size-4 shrink-0 text-muted-foreground" />
        <span class="truncate">{{ VISIBILITY_META[visibility].short }}</span>
        <template v-if="collectionName">
          <span class="text-muted-foreground/60">·</span>
          <FolderOpen class="size-4 shrink-0 text-muted-foreground" />
          <span class="truncate text-muted-foreground">{{ collectionName }}</span>
        </template>
        <ChevronDown class="size-3.5 shrink-0 text-muted-foreground" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-80 p-3" align="end">
      <div class="space-y-3">
        <div>
          <p class="text-xs font-medium text-muted-foreground mb-1.5">
            {{ t('sharing.visibilityHeading') }}
          </p>
          <div class="space-y-1">
            <button
              v-for="v in VISIBILITY_ORDER"
              :key="v"
              type="button"
              class="w-full flex items-start gap-2.5 rounded-md p-2 text-left transition-colors hover:bg-muted/50"
              :class="visibility === v ? 'bg-primary/[0.06] ring-1 ring-primary/30' : ''"
              :disabled="saving"
              @click="setVisibility(v)"
            >
              <component :is="ICONS[v]" class="size-4 mt-0.5 shrink-0 text-muted-foreground" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium">{{ VISIBILITY_META[v].label }}</span>
                <span class="block text-xs text-muted-foreground">
                  {{ VISIBILITY_META[v].description }}
                </span>
              </span>
              <Check v-if="visibility === v" class="size-4 mt-0.5 shrink-0 text-primary" />
            </button>
          </div>
        </div>

        <div class="border-t pt-3">
          <p class="text-xs font-medium text-muted-foreground mb-1.5">
            {{ t('sharing.collectionHeading') }}
          </p>
          <div v-if="loadingCollections" class="py-2 text-center">
            <Loader2 class="size-4 animate-spin inline-block text-muted-foreground" />
          </div>
          <div v-else class="space-y-1 max-h-44 overflow-y-auto">
            <button
              type="button"
              class="w-full flex items-center gap-2.5 rounded-md p-2 text-left text-sm transition-colors hover:bg-muted/50"
              :class="!collectionName ? 'bg-primary/[0.06] ring-1 ring-primary/30' : ''"
              :disabled="saving"
              @click="setCollection('')"
            >
              <span class="min-w-0 flex-1 text-muted-foreground">
                {{ t('sharing.noCollection') }}
              </span>
              <Check v-if="!collectionName" class="size-4 shrink-0 text-primary" />
            </button>
            <button
              v-for="col in collections"
              :key="col.name"
              type="button"
              class="w-full flex items-center gap-2.5 rounded-md p-2 text-left text-sm transition-colors hover:bg-muted/50"
              :class="isSelectedCollection(col.name) ? 'bg-primary/[0.06] ring-1 ring-primary/30' : ''"
              :disabled="saving"
              @click="setCollection(col.name)"
            >
              <FolderOpen class="size-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0 flex-1 truncate">{{ col.name }}</span>
              <Check v-if="isSelectedCollection(col.name)" class="size-4 shrink-0 text-primary" />
            </button>
          </div>
          <div class="flex items-center gap-2 pt-2">
            <Input
              v-model="newName"
              :placeholder="t('sharing.newCollectionPlaceholder')"
              class="h-8 text-sm"
              @keyup.enter="createAndSelect"
            />
            <Button
              variant="outline"
              size="sm"
              class="shrink-0"
              :disabled="saving || !newName.trim()"
              @click="createAndSelect"
            >
              {{ t('sharing.use') }}
            </Button>
          </div>
        </div>

        <p class="text-[11px] text-muted-foreground">
          {{ t('sharing.appliesEverywhere') }}
        </p>
      </div>
    </PopoverContent>
  </Popover>
</template>
