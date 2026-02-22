<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
})

const segments = computed(() => props.data?.segments || [])

const speakers = computed(() => {
  const s = new Set()
  for (const seg of segments.value) {
    if (seg?.speaker) s.add(seg.speaker)
  }
  return [...s]
})

const palette = [
  '#4f46e5', // indigo
  '#0ea5e9', // sky
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#a855f7', // purple
  '#14b8a6', // teal
  '#f97316', // orange
]

function hashString(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h
}

function colorForSpeaker(speaker) {
  if (!speaker) return '#64748b'
  return palette[hashString(String(speaker)) % palette.length]
}

function formatTs(sec) {
  const s = Math.max(0, Number(sec || 0))
  const ms = Math.floor((s % 1) * 1000)
  const total = Math.floor(s)
  const ss = total % 60
  const mm = Math.floor(total / 60) % 60
  const hh = Math.floor(total / 3600)
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}.${pad(ms, 3)}`
}
</script>

<template>
  <div class="w-full">
    <div v-if="!data" class="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
      Результат появится здесь после завершения транскрибации.
    </div>

    <div v-else class="rounded-2xl border border-slate-200 bg-white">
      <div class="border-b border-slate-200 p-5">
        <div class="text-sm font-medium text-slate-900">Транскрипт</div>
        <div class="mt-1 text-xs text-slate-600">
          Сегментов: <span class="font-medium text-slate-800">{{ segments.length }}</span>
        </div>
        <div v-if="speakers.length" class="mt-4 flex flex-wrap gap-2">
          <div
            v-for="sp in speakers"
            :key="sp"
            class="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700"
          >
            <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: colorForSpeaker(sp) }" />
            <span class="font-medium">{{ sp }}</span>
          </div>
        </div>
      </div>

      <div class="max-h-[60vh] overflow-auto p-5">
        <div v-if="!segments.length" class="text-sm text-slate-600">Пусто.</div>

        <div v-for="(seg, idx) in segments" :key="idx" class="mb-4">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <span
                v-if="seg.speaker"
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium text-white"
                :style="{ backgroundColor: colorForSpeaker(seg.speaker) }"
              >
                {{ seg.speaker }}
              </span>
              <span class="text-xs text-slate-600 tabular-nums">
                {{ formatTs(seg.start) }} – {{ formatTs(seg.end) }}
              </span>
            </div>
          </div>

          <div class="mt-1 text-sm leading-relaxed text-slate-900 whitespace-pre-wrap">
            {{ (seg.text || '').trim() }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

