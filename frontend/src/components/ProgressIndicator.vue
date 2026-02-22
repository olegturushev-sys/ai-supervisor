<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: String, default: '' },
  stage: { type: String, default: '' },
  progress: { type: Number, default: 0 },
  hasDiarization: { type: Boolean, default: false },
})

const percent = computed(() => Math.round(Math.max(0, Math.min(1, props.progress)) * 100))

const label = computed(() => {
  if (props.state === 'error') return 'Ошибка'
  if (props.state === 'done') return 'Готово'

  switch (props.stage) {
    case 'upload':
      return 'Загрузка…'
    case 'convert':
      return 'Конвертация…'
    case 'transcribe':
      return 'Транскрибация…'
    case 'align':
      return props.hasDiarization ? 'Выравнивание / Диаризация…' : 'Выравнивание…'
    case 'write':
      return 'Сохранение…'
    default:
      return 'В очереди…'
  }
})
</script>

<template>
  <div class="w-full rounded-2xl border border-slate-200 bg-white p-5">
    <div class="flex items-center justify-between gap-4">
      <div class="text-sm font-medium text-slate-900">{{ label }}</div>
      <div class="text-xs text-slate-600 tabular-nums">{{ percent }}%</div>
    </div>
    <div class="mt-3 h-2 w-full rounded-full bg-slate-100 overflow-hidden">
      <div
        class="h-full rounded-full bg-indigo-500 transition-[width] duration-300"
        :style="{ width: `${percent}%` }"
      />
    </div>
  </div>
</template>

