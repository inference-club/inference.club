import type { Visibility } from '@/types'

// Display metadata for each visibility level. Icons are mapped in components
// (VisibilityBadge) so this stays free of Vue/lucide imports.
export const VISIBILITY_META: Record<
  Visibility,
  { label: string; short: string; description: string }
> = {
  PUBLIC: {
    label: 'Public',
    short: 'Public',
    description: 'Anyone can view it, and it shows on your public profile.',
  },
  UNLISTED: {
    label: 'Unlisted',
    short: 'Unlisted',
    description:
      'Anyone with the link can view it, but it is not listed on your public profile.',
  },
  PRIVATE: {
    label: 'Members only',
    short: 'Members',
    description: 'Any signed-in inference.club member can view it.',
  },
  SECRET: {
    label: 'Only me',
    short: 'Only me',
    description: 'Only you can view this.',
  },
}

// Order shown in pickers (most open → most private).
export const VISIBILITY_ORDER: Visibility[] = [
  'PUBLIC',
  'UNLISTED',
  'PRIVATE',
  'SECRET',
]
