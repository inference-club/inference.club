// Standard ⌘/Ctrl+Enter "start a generation" shortcut, shared across every
// playground page. A window-level keydown means the shortcut fires no matter
// which control (prompt, options sidebar, a Select) currently has focus, so the
// behaviour is identical everywhere. The handler guards itself — most page
// run()/send() functions early-return when the form is incomplete or a request
// is already in flight, so a stray press is a no-op.
import { onBeforeUnmount, onMounted } from 'vue'

export function useSubmitHotkey(handler: () => void) {
  const onKey = (e: KeyboardEvent) => {
    // `isComposing` guards against firing mid-IME-composition (e.g. typing CJK).
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.isComposing) {
      e.preventDefault()
      handler()
    }
  }
  onMounted(() => window.addEventListener('keydown', onKey))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
}
