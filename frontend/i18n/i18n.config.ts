// Runtime vue-i18n config. fallbackLocale ensures any key missing in the
// active locale renders the English string instead of a raw key — this is what
// lets us ship translations incrementally (e.g. dashboard before it's fully
// localized) without ever showing `nav.dashboard` to a user.
export default defineI18nConfig(() => ({
  legacy: false,
  fallbackLocale: 'en',
  // Don't warn in the console for every not-yet-translated key; the fallback
  // behavior is intentional and expected while locales are filled in.
  missingWarn: false,
  fallbackWarn: false,
}))
