const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function url(path) {
  if (!path.startsWith('/')) path = `/${path}`
  return `${API_BASE}${path}`
}

async function httpJson(path, options = {}) {
  // #region agent log
  fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H1',location:'frontend/src/services/api.js:httpJson',message:'httpJson request',data:{apiBase:API_BASE,path,method:(options.method||'GET')},timestamp:Date.now()})}).catch(()=>{});
  // #endregion
  let res
  try {
    res = await fetch(url(path), options)
  } catch (e) {
    // #region agent log
    fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H5',location:'frontend/src/services/api.js:httpJson',message:'fetch threw',data:{apiBase:API_BASE,path,error:String(e?.message||e)},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    throw e
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    // #region agent log
    fetch('http://127.0.0.1:7504/ingest/b959b393-85a0-4667-bafc-8d33683b4cb1',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8957bd'},body:JSON.stringify({sessionId:'8957bd',runId:'pre-fix',hypothesisId:'H1',location:'frontend/src/services/api.js:httpJson',message:'httpJson error',data:{apiBase:API_BASE,path,status:res.status,bodyPreview:(text||'').slice(0,200)},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
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

