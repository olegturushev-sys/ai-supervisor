<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import FileUploader from './components/FileUploader.vue'
import ProgressIndicator from './components/ProgressIndicator.vue'
import TranscriptViewer from './components/TranscriptViewer.vue'

import { getMarkdown, getStatus, getTranscriptData, transcribe, triggerAnalysis } from './services/api'

const file = ref(null)
const taskId = ref('')
const status = ref(null)
const transcriptData = ref(null)
const isStarting = ref(false)
const error = ref('')
const didAutoDownload = ref(false)

let pollTimer = null

const hasDiarization = computed(() => {
  // heuristics: if transcript has speaker fields or the backend produced them.
  const segs = transcriptData.value?.segments || []
  return segs.some((s) => !!s?.speaker)
})

const canStart = computed(() => !!file.value && !isStarting.value)
const isRunning = computed(() => ['queued', 'running'].includes(status.value?.state))
const isDone = computed(() => status.value?.state === 'done')
const isError = computed(() => status.value?.state === 'error')

function reset() {
  file.value = null
  taskId.value = ''
  status.value = null
  transcriptData.value = null
  isStarting.value = false
  error.value = ''
  didAutoDownload.value = false
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

async function start() {
  if (!file.value) return
  // Keep the selected file, but reset the run state.
  const selected = file.value
  reset()
  file.value = selected
  isStarting.value = true
  error.value = ''
  try {
    const r = await transcribe(file.value)
    taskId.value = r.task_id || r.job_id
    // #region agent log
    fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H2',location:'frontend/src/App.vue:start',message:'transcribe started',data:{taskId:taskId.value},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    await poll()
  } catch (e) {
    error.value = String(e?.message || e)
    // #region agent log
    fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H5',location:'frontend/src/App.vue:start',message:'start error',data:{error:String(e?.message||e)},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
  } finally {
    isStarting.value = false
  }
}

async function poll() {
  if (!taskId.value) return
  try {
    status.value = await getStatus(taskId.value)
    // #region agent log
    fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H3',location:'frontend/src/App.vue:poll',message:'status polled',data:{taskId:taskId.value,state:status.value?.state,stage:status.value?.stage,progress:status.value?.progress},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    if (status.value.state === 'done') {
      transcriptData.value = await getTranscriptData(taskId.value)
      if (!didAutoDownload.value) {
        didAutoDownload.value = true
        await downloadMarkdown()
      }
      return
    }
    if (status.value.state === 'error') {
      error.value = status.value.error || 'Ошибка обработки'
      return
    }
  } catch (e) {
    error.value = String(e?.message || e)
    return
  }
  pollTimer = setTimeout(poll, 750)
}

async function downloadMarkdown() {
  if (!taskId.value) return
  const text = await getMarkdown(taskId.value)
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${taskId.value}.md`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

async function downloadAnalysis() {
  if (!taskId.value) return
  try {
    error.value = 'Запрос анализа...'
    await triggerAnalysis(taskId.value)
    error.value = ''
    const text = await getMarkdown(taskId.value + '_analysis')
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${taskId.value}_analysis.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  } catch (e) {
    error.value = 'Ошибка анализа: ' + String(e?.message || e)
  }
}

onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

watch(file, () => {
  // changing the file should reset current run
  if (taskId.value) reset()
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <div class="mx-auto max-w-4xl px-5 py-10">
      <header class="mb-8">
        <div class="text-sm font-medium text-slate-600">Note Therapy</div>
        <h1 class="mt-2 text-2xl font-semibold text-slate-900">Транскрибация аудио</h1>
        <p class="mt-2 text-sm text-slate-600">
          Загрузка → прогресс → результат по спикерам → экспорт Markdown
        </p>
      </header>

      <div class="grid gap-6">
        <FileUploader v-model="file" />

        <div class="flex flex-wrap gap-3">
          <button
            class="inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!canStart"
            @click="start"
          >
            Начать транскрибацию
          </button>

          <button
            class="inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium border border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
            :disabled="!taskId"
            @click="downloadMarkdown"
          >
            Скачать Markdown
          </button>

          <button
            class="inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium border border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
            :disabled="!isDone"
            @click="downloadAnalysis"
          >
            Скачать анализ
          </button>

          <button
            class="inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium border border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
            @click="reset"
          >
            Сброс
          </button>
        </div>

        <div v-if="error" class="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {{ error }}
        </div>

        <ProgressIndicator
          v-if="status"
          :state="status.state"
          :stage="status.stage"
          :progress="status.progress"
          :has-diarization="hasDiarization"
        />

        <TranscriptViewer :data="transcriptData" />
      </div>
    </div>
  </div>
</template>
