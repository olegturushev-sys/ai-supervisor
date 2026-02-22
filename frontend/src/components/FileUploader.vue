<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: File, default: null },
})
const emit = defineEmits(['update:modelValue'])

const isDragging = ref(false)
const error = ref('')

const prettySize = computed(() => {
  if (!props.modelValue) return ''
  const bytes = props.modelValue.size
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
})

function isAllowed(file) {
  const name = (file?.name || '').toLowerCase()
  return name.endsWith('.mp3') || name.endsWith('.wav') || name.endsWith('.m4a')
}

function setFile(file) {
  error.value = ''
  if (!file) return
  if (!isAllowed(file)) {
    error.value = 'Поддерживаются только mp3, wav, m4a.'
    emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', file)
}

function onDrop(e) {
  e.preventDefault()
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  setFile(file)
}
</script>

<template>
  <div class="w-full">
    <div
      class="rounded-2xl border border-dashed p-8 transition bg-white/70 backdrop-blur"
      :class="isDragging ? 'border-indigo-400 bg-indigo-50' : 'border-slate-300'"
      @dragenter.prevent="isDragging = true"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop="onDrop"
    >
      <div class="flex flex-col items-center gap-2 text-center">
        <div class="text-sm font-medium text-slate-900">Перетащи аудиофайл сюда</div>
        <div class="text-xs text-slate-600">mp3 · wav · m4a</div>

        <label
          class="mt-4 inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium bg-slate-900 text-white hover:bg-slate-800 cursor-pointer"
        >
          Выбрать файл
          <input
            class="hidden"
            type="file"
            accept=".mp3,.wav,.m4a,audio/*"
            @change="(e) => setFile(e.target.files?.[0])"
          />
        </label>

        <div v-if="modelValue" class="mt-4 w-full rounded-xl bg-slate-50 p-4 text-left">
          <div class="text-sm font-medium text-slate-900 truncate">{{ modelValue.name }}</div>
          <div class="text-xs text-slate-600">{{ prettySize }}</div>
        </div>

        <div v-if="error" class="mt-3 text-sm text-rose-600">{{ error }}</div>
      </div>
    </div>
  </div>
</template>

