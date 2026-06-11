<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button variant="ghost" size="sm" class="gap-1 px-1.5 sm:px-2" :aria-label="t('nav.selectLanguage')">
        <Languages class="hidden sm:block h-5 w-5" />
        <span class="text-xs font-medium uppercase tracking-wide">{{ currentShort }}</span>
        <ChevronDown class="h-3 w-3 opacity-60" />
        <span class="sr-only">{{ t('nav.selectLanguage') }}</span>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-48 p-1" align="end">
      <button
        v-for="loc in availableLocales"
        :key="loc.code"
        type="button"
        class="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none"
        :class="loc.code === locale ? 'font-medium text-foreground' : 'text-muted-foreground'"
        @click="choose(loc.code)"
      >
        <span>{{ loc.name }}</span>
        <Check v-if="loc.code === locale" class="h-4 w-4 text-primary" />
      </button>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Languages, Check, ChevronDown } from 'lucide-vue-next'

// useI18n / useSwitchLocalePath are auto-imported by @nuxtjs/i18n.
const { t, locale, locales } = useI18n()
const switchLocalePath = useSwitchLocalePath()

// The configured locales (objects with code + native `name`), narrowed past the
// string-array shape the type allows.
const availableLocales = computed(() =>
  (locales.value as Array<{ code: string, name?: string }>).filter(l => !!l.name),
)

// Short label in the trigger: the locale code (EN, JA…) reads cleaner than the
// full native name in a tight toolbar.
const currentShort = computed(() => String(locale.value).toUpperCase())

function choose(code: string) {
  // Navigate to the same route in the target locale. @nuxtjs/i18n updates the
  // i18n_locale cookie as part of the navigation, so the choice persists.
  const path = switchLocalePath(code)
  if (path) navigateTo(path)
}
</script>
