import { onBeforeUnmount, ref } from 'vue'

export function useGraphUiAutosave(delayMs = 500) {
  const timerId = ref<number | null>(null)

  function clearAutosaveTimer() {
    if (timerId.value == null) {
      return
    }
    window.clearTimeout(timerId.value)
    timerId.value = null
  }

  function scheduleAutosave(callback: () => void | Promise<void>) {
    clearAutosaveTimer()
    timerId.value = window.setTimeout(() => {
      timerId.value = null
      void callback()
    }, delayMs)
  }

  onBeforeUnmount(clearAutosaveTimer)

  return {
    clearAutosaveTimer,
    scheduleAutosave,
  }
}
