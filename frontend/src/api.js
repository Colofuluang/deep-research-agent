async function requestJson(url, options) {
  const response = await fetch(url, options)
  if (!response.ok) {
    let detail
    try { detail = (await response.json()).detail } catch { /* Some proxies return plain text. */ }
    throw new Error(typeof detail === 'string' ? detail : `研究请求失败：HTTP ${response.status}`)
  }
  return response.json()
}

export const createResearchJob = (topic, requestId) => requestJson('/api/research/jobs', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ topic, request_id: requestId }),
})
export const resumeResearchJob = (runId) => requestJson(`/api/research/${encodeURIComponent(runId)}/jobs`, { method: 'POST' })
export const listResearchJobs = () => requestJson('/api/research/jobs?include_deleted=true')
export const deleteResearchRun = (runId) => requestJson(`/api/research/${encodeURIComponent(runId)}`, { method: 'DELETE' })
export const getResearchJob = (jobId) => requestJson(`/api/research/jobs/${encodeURIComponent(jobId)}`)
export const stopResearchJob = (jobId) => requestJson(`/api/research/jobs/${encodeURIComponent(jobId)}/stop`, { method: 'POST' })

export async function subscribeResearchJob(jobId, onEvent, { after = 0, signal } = {}) {
  const response = await fetch(`/api/research/jobs/${encodeURIComponent(jobId)}/events?after=${after}`, {
    headers: { Accept: 'text/event-stream' }, signal,
  })
  if (!response.ok) throw new Error(`进度订阅失败：HTTP ${response.status}`)
  if (!response.body) throw new Error('浏览器未提供响应流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const cancelReader = () => { void reader.cancel().catch(() => {}) }
  signal?.addEventListener('abort', cancelReader, { once: true })
  try {
    while (!signal?.aborted) {
      const { value, done } = await reader.read()
      if (done) {
        if (signal?.aborted) return
        throw new Error('进度连接已结束，后台任务状态将重新同步')
      }
      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      let boundary
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const lines = buffer.slice(0, boundary).split('\n')
        buffer = buffer.slice(boundary + 2)
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (!data) continue
        const id = Number(lines.find(line => line.startsWith('id:'))?.slice(3).trim())
        const event = {
          id: Number.isSafeInteger(id) && id >= 0 ? id : null,
          event: lines.find(line => line.startsWith('event:'))?.slice(6).trim() || 'message',
          data: JSON.parse(data),
        }
        onEvent(event)
        if (event.event === 'completed' || event.event === 'error'
          || (event.event === 'job_status' && ['completed', 'stopped', 'failed', 'interrupted', 'deleted'].includes(event.data.status))) return
      }
    }
  } finally {
    signal?.removeEventListener('abort', cancelReader)
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
