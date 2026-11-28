<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { ArrowLeft, Trash2, SlidersHorizontal } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { usePlaygroundPrefill, REPRODUCE_ROUTES } from '@/composables/usePlaygroundPrefill'
import { useAuth } from '@/composables/useAuth'
import { requestTitle } from '@/utils/requestView'

definePageMeta({
  layout: 'app',
})

const { t } = useI18n()
const route = useRoute()
const store = useInferenceRequestStore()
const { isAuthenticated } = useAuth()
const id = computed(() => String(route.params.id))

// Public request detail is open to anyone (the API enforces per-request
// visibility); send logged-out viewers back to the public gallery rather than
// the members-only requests list.
const backTo = computed(() =>
  isAuthenticated.value ? '/dashboard/inference/requests' : '/dashboard/inference/gallery',
)

const req = computed(() => store.currentRequest)

useHead(() => ({
  title: req.value ? requestTitle(req.value, t(`request.kind.${req.value.inference_type}`)) : undefined,
}))

const remove = async () => {
  try {
    await store.deleteRequest(id.value)
    toast.success(t('request.deleted'))
    navigateTo('/dashboard/inference/requests')
  } catch {
    toast.error(t('request.deleteFailed'))
  }
}

// After an in-place retry, pull the fresh result back in.
const onRetried = () => {
  store.fetchRequest(id.value).catch(() => {})
}

// "Reproduce in playground" — open the matching composer pre-filled with this
// request's parameters so the user can tweak and regenerate.
const prefill = usePlaygroundPrefill()
const reproduceRoute = computed(() =>
  req.value ? REPRODUCE_ROUTES[req.value.inference_type] : undefined,
)
const reproduce = () => {
  if (!req.value || !reproduceRoute.value) return
  prefill.set(req.value.inference_type, {
    ...(req.value.payload || {}),
    model: req.value.model_name,
  })
  navigateTo(reproduceRoute.value)
}

onMounted(() => {
  store.fetchRequest(id.value).catch(() => {})
})
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-3 py-5 sm:px-6 sm:py-6">
    <NuxtLink
      :to="backTo"
      class="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" /> {{ isAuthenticated ? t('request.back') : t('request.backGallery') }}
    </NuxtLink>

    <div v-if="store.loading && !req" class="space-y-4">
      <div class="h-8 w-64 animate-pulse rounded bg-muted" />
      <div class="h-72 animate-pulse rounded-2xl bg-muted" />
      <div class="h-20 animate-pulse rounded-2xl bg-muted" />
    </div>

    <div v-else-if="store.error" class="py-12 text-center text-destructive">
      {{ store.error }}
    </div>

    <RequestView v-else-if="req" :request="req">
      <template #actions>
        <RequestActionBar
          :request="req"
          @visibility-change="(v) => { if (store.currentRequest) store.currentRequest.visibility = v }"
          @retried="onRetried"
        />
        <ShareButton
          v-if="!req.is_owner && (req.visibility === 'PUBLIC' || req.visibility === 'UNLISTED')"
          icon-only
          variant="ghost"
        />
        <Button
          v-if="req.is_owner && reproduceRoute"
          variant="outline"
          size="sm"
          class="gap-2"
          :title="t('request.reproduce')"
          data-testid="request-reproduce"
          @click="reproduce"
        >
          <SlidersHorizontal class="size-4" />
          <span class="hidden sm:inline">{{ t('request.reproduce') }}</span>
        </Button>
        <AlertDialog v-if="req.is_owner">
          <AlertDialogTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 text-muted-foreground hover:text-destructive"
              :title="t('request.delete')"
              :aria-label="t('request.delete')"
            >
              <Trash2 class="size-4" />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{{ t('request.deleteTitle') }}</AlertDialogTitle>
              <AlertDialogDescription>{{ t('request.deleteBody') }}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{{ t('common.cancel') }}</AlertDialogCancel>
              <AlertDialogAction class="bg-destructive text-white hover:bg-destructive/90" @click="remove">
                {{ t('request.delete') }}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </template>
    </RequestView>
  </div>
</template>
