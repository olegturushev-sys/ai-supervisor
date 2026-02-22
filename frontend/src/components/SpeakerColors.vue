<script setup>
import { computed } from 'vue'

const props = defineProps({
  speakers: { type: Array, default: () => [] },
  colorFor: { type: Function, required: true },
})

const sorted = computed(() => [...new Set(props.speakers)].sort())
</script>

<template>
  <div v-if="sorted.length" class="flex flex-wrap gap-2">
    <div
      v-for="sp in sorted"
      :key="sp"
      class="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700"
    >
      <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: colorFor(sp) }" />
      <span class="font-medium">{{ sp }}</span>
    </div>
  </div>
</template>

