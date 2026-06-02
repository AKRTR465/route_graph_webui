import { reactive } from 'vue'

export function usePlannerForm<T extends object>(defaults: T) {
  const form = reactive({ ...defaults }) as T

  function resetPlannerForm(nextDefaults: T = defaults) {
    Object.assign(form, nextDefaults)
  }

  return {
    form,
    resetPlannerForm,
  }
}
