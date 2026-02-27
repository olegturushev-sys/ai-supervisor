const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function url(path) {
  if (!path.startsWith('/')) path = `/${path}`
  return `${API_BASE}${path}`
}

async function httpJson(path, options = {}) {
  let res
  try {
    res = await fetch(url(path), options)
  } catch (e) {
    throw e
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function transcribe(file) {
  const form = new FormData()
  form.append('file', file)
  return await httpJson('/transcribe', { method: 'POST', body: form })
}

export async function getStatus(taskId) {
  return await httpJson(`/status/${encodeURIComponent(taskId)}`)
}

export async function getMarkdown(taskId) {
  const res = await fetch(url(`/download/${encodeURIComponent(taskId)}.md`))
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status}`)
  }
  return await res.text()
}

export async function getTranscriptData(taskId) {
  return await httpJson(`/jobs/${encodeURIComponent(taskId)}/data`)
}

export async function triggerAnalysis(taskId) {
  return await httpJson(`/jobs/${encodeURIComponent(taskId)}/analyze`, { method: 'POST' })
}
