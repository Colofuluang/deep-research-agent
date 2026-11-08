import { computed, reactive, ref } from 'vue'
import { createResearchJob, resumeResearchJob, listResearchJobs, getResearchJob, stopResearchJob, deleteResearchRun, subscribeResearchJob } from './api.js'

const RUN_ID = /^[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$/
const JOB_ID = /^[0-9a-f]{32}$/
const ACTIVE = new Set(['queued', 'running', 'stopping'])
const STORAGE_KEY = 'deep-research-history-v1'
const ACTIVE_KEY = 'deep-research-active-run'
const DELETED_KEY = 'deep-research-deleted-runs-v1'

export function useResearch() {
  const topic = ref('')
  const resumeId = ref('')
  const inputError = ref('')
  const resumeError = ref('')
  const storageNotice = ref('')
  const pendingRecord = ref(null)
  let storage
  let pollTimer
  let connection
  let disposed = false
  let syncing = false
  let refreshRequested = false
  try { storage = globalThis.localStorage } catch { /* Browser storage can be disabled. */ }
  const deletedRuns = new Set(readDeleted())

  function readDeleted() {
    try {
      const saved = JSON.parse(storage?.getItem(DELETED_KEY) ?? '[]')
      return Array.isArray(saved) ? saved.filter(id => typeof id === 'string' && RUN_ID.test(id)) : []
    } catch { return [] }
  }

  function readHistory() {
    try {
      const saved = JSON.parse(storage?.getItem(STORAGE_KEY) ?? '[]')
      if (!Array.isArray(saved)) return []
      const seen = new Set()
      return saved.filter(item => {
        if (!item || typeof item.runId !== 'string' || !RUN_ID.test(item.runId) || deletedRuns.has(item.runId) || typeof item.topic !== 'string' || seen.has(item.runId)) return false
        seen.add(item.runId)
        return true
      }).slice(0, 20).map(item => {
        const jobId = typeof item.jobId === 'string' && JOB_ID.test(item.jobId) ? item.jobId : ''
        const status = item.status === 'completed' ? 'completed'
          : jobId && ['queued', 'running', 'stopping', 'stopped', 'failed', 'interrupted'].includes(item.status) ? item.status : 'interrupted'
        return {
          id: item.runId, runId: item.runId, jobId, topic: item.topic,
          report: typeof item.report === 'string' ? item.report : '',
          reportSummary: typeof item.reportSummary === 'string' ? item.reportSummary : '',
          status, message: status === 'completed' ? '研究已完成' : jobId ? '正在同步后台状态……' : '可继续恢复研究。',
          completedTasks: Number.isInteger(item.completedTasks) ? item.completedTasks : 0,
          tasks: [], cursor: 0, jobCreatedAt: Number(item.jobCreatedAt) || 0,
          updatedAt: Number.isFinite(item.updatedAt) ? item.updatedAt : Date.now(),
        }
      })
    } catch {
      storageNotice.value = '本地缓存无法读取，研究记录可从后台列表同步。'
      return []
    }
  }

  const history = ref(readHistory())
  let savedActive = ''
  try { savedActive = storage?.getItem(ACTIVE_KEY) ?? '' } catch { /* Optional view cache. */ }
  const activeId = ref(history.value.some(item => item.id === savedActive) ? savedActive : '')
  const activeResearch = computed(() => history.value.find(item => item.id === activeId.value)
    ?? (pendingRecord.value?.id === activeId.value ? pendingRecord.value : null))
  const report = computed(() => activeResearch.value?.report ?? '')
  const sending = computed(() => ACTIVE.has(activeResearch.value?.status) || activeResearch.value?.status === 'submitting')

  function saveActive() {
    try { storage?.setItem(ACTIVE_KEY, activeResearch.value?.runId ?? '') } catch { /* The task is stored on the server. */ }
  }

  function persistHistory() {
    const records = history.value.filter(item => RUN_ID.test(item.runId)).slice(0, 20).map(item => ({
      runId: item.runId, jobId: item.jobId, topic: item.topic, status: item.status,
      report: item.report, reportSummary: item.reportSummary, completedTasks: item.completedTasks,
      updatedAt: item.updatedAt, jobCreatedAt: item.jobCreatedAt,
    }))
    try {
      if (!storage) throw new Error('Storage unavailable')
      storage.setItem(STORAGE_KEY, JSON.stringify(records))
    } catch {
      storageNotice.value = '浏览器未能完整缓存记录，结果仍保存在后台。'
      try { storage?.setItem(STORAGE_KEY, JSON.stringify(records.map(({ report, ...item }) => item))) } catch { /* Server results remain available. */ }
    }
    saveActive()
  }

  function rememberRecord(entry) {
    if (deletedRuns.has(entry.runId)) return
    if (!history.value.some(item => item.id === entry.id)) {
      history.value = [entry, ...history.value.filter(item => item.runId !== entry.runId)].slice(0, 20)
    }
    if (pendingRecord.value?.id === entry.id) pendingRecord.value = null
  }

  function createRecord(title, runId = '') {
    const entry = reactive({
      id: globalThis.crypto.randomUUID(), runId, jobId: '', topic: title,
      status: 'submitting', message: '正在提交后台任务……', report: '', reportSummary: '',
      tasks: [], cursor: 0, completedTasks: 0, updatedAt: Date.now(), jobCreatedAt: 0,
    })
    pendingRecord.value = entry
    activeId.value = entry.id
    return entry
  }

  function disconnect() {
    connection?.controller.abort()
    connection = null
  }

  function forgetRuns(ids) {
    for (const id of [...readDeleted(), ...ids]) if (RUN_ID.test(id)) deletedRuns.add(id)
    if (deletedRuns.has(activeResearch.value?.runId)) {
      disconnect()
      activeId.value = ''
      topic.value = ''
    }
    history.value = history.value.filter(item => !deletedRuns.has(item.runId))
    if (deletedRuns.has(pendingRecord.value?.runId)) pendingRecord.value = null
    try { storage?.setItem(DELETED_KEY, JSON.stringify([...deletedRuns].sort())) } catch { /* Server tombstones remain authoritative. */ }
    persistHistory()
  }

  function onStorage(event) {
    if (event.key === DELETED_KEY) forgetRuns(readDeleted())
  }
  globalThis.addEventListener?.('storage', onStorage)

  function newResearch() {
    disconnect()
    activeId.value = ''
    topic.value = ''
    inputError.value = ''
    resumeError.value = ''
    saveActive()
  }

  function setTasks(entry, items, completedNumbers = []) {
    const completed = new Set(completedNumbers.map(Number))
    entry.tasks = items.filter(item => item && Number.isInteger(Number(item.task_number))).map(item => ({
      number: Number(item.task_number), title: item.title || `研究任务 ${item.task_number}`,
      status: completed.has(Number(item.task_number)) ? 'completed' : 'waiting',
      latestMessage: completed.has(Number(item.task_number)) ? '研究成果已保存' : '等待执行',
    }))
  }

  function markUnfinished(entry, status) {
    for (const task of entry.tasks) if (task.status !== 'completed') task.status = status
  }

  function handleEvent(entry, event) {
    const data = event.data ?? {}
    if (event.event === 'job_status' && data.status === 'deleted') {
      forgetRuns([entry.runId])
      return
    }
    if (deletedRuns.has(entry.runId)) return
    if (Number.isSafeInteger(event.id)) entry.cursor = Math.max(entry.cursor, event.id)
    if (event.event === 'started') {
      if (typeof data.topic === 'string' && data.topic.trim()) entry.topic = data.topic
      entry.status = 'running'
      entry.message = data.mode === 'resume' ? '正在恢复研究……' : '研究已启动'
      setTasks(entry, data.tasks ?? [], data.completed_task_numbers ?? [])
    } else if (event.event === 'progress') {
      if (Array.isArray(data.tasks)) setTasks(entry, data.tasks)
      if (data.task_number != null) {
        const number = Number(data.task_number)
        let task = entry.tasks.find(item => item.number === number)
        if (!task) {
          task = reactive({ number, title: `研究任务 ${number}`, status: 'waiting', latestMessage: '' })
          entry.tasks.push(task)
          entry.tasks.sort((a, b) => a.number - b.number)
        }
        if (task.status !== 'completed') {
          task.latestMessage = data.message ?? task.latestMessage
          task.status = data.stage === 'persist' ? 'completed' : 'running'
        }
      } else if (data.message) entry.message = data.message
    } else if (event.event === 'completed') {
      entry.report = typeof data.report === 'string' ? data.report : ''
      entry.reportSummary = typeof data.report_summary === 'string' ? data.report_summary.trim() : ''
      entry.status = 'completed'
      entry.message = '研究已完成'
      entry.completedTasks = data.completed_tasks ?? entry.tasks.length
      for (const task of entry.tasks) { task.status = 'completed'; task.latestMessage = '研究成果已保存' }
    } else if (event.event === 'error') {
      entry.status = 'failed'
      entry.message = data.message || '研究中断，可从检查点恢复。'
      markUnfinished(entry, 'interrupted')
    } else if (event.event === 'job_status') {
      entry.status = data.status
      entry.message = data.message ?? entry.message
      if (['stopped', 'failed', 'interrupted'].includes(data.status)) markUnfinished(entry, data.status === 'stopped' ? 'stopped' : 'interrupted')
    }
    entry.updatedAt = Date.now()
    persistHistory()
  }

  function applySnapshot(entry, job) {
    if (!JOB_ID.test(job.job_id) || !RUN_ID.test(job.run_id)) throw new Error('后台返回了无效任务编号')
    if (deletedRuns.has(job.run_id)) {
      entry.runId = job.run_id
      forgetRuns([job.run_id])
      return
    }
    if (entry.jobCreatedAt > job.created_at) return
    if (entry.jobId === job.job_id && !ACTIVE.has(entry.status) && entry.status !== 'submitting' && ACTIVE.has(job.status)) return
    if (entry.jobId !== job.job_id) { entry.cursor = 0; entry.tasks = [] }
    entry.jobId = job.job_id
    entry.runId = job.run_id
    entry.topic = job.topic
    entry.status = job.status
    entry.message = job.message || '正在同步后台状态……'
    entry.jobCreatedAt = job.created_at
    entry.updatedAt = job.updated_at * 1000
    rememberRecord(entry)
    if (job.result) handleEvent(entry, { event: 'completed', data: job.result })
    else if (['stopped', 'failed', 'interrupted'].includes(job.status)) markUnfinished(entry, job.status === 'stopped' ? 'stopped' : 'interrupted')
    persistHistory()
  }

  function schedulePoll() {
    clearTimeout(pollTimer)
    if (!disposed && history.value.some(item => ACTIVE.has(item.status))) {
      pollTimer = setTimeout(() => { void loadJobs() }, 3000)
      pollTimer.unref?.()
    }
  }

  async function follow(entry) {
    if (disposed || !entry?.jobId || entry.deleting || deletedRuns.has(entry.runId) || activeId.value !== entry.id) return
    if (connection?.jobId === entry.jobId) return
    if (entry.status === 'completed' && entry.report) return
    if (!ACTIVE.has(entry.status) && entry.status !== 'completed' && entry.cursor > 0) return
    disconnect()
    const controller = new AbortController()
    const jobId = entry.jobId
    connection = { controller, jobId }
    try {
      await subscribeResearchJob(jobId, event => {
        if (!controller.signal.aborted && entry.jobId === jobId) handleEvent(entry, event)
      }, { after: entry.cursor, signal: controller.signal })
    } catch (error) {
      if (!controller.signal.aborted && !disposed && entry.jobId === jobId) {
        try {
          const snapshot = await getResearchJob(jobId)
          if (!controller.signal.aborted && entry.jobId === jobId) applySnapshot(entry, snapshot)
        }
        catch {
          entry.message = error.message || '进度暂不可用，后台任务状态将重新同步。'
          void loadJobs()
        }
      }
    } finally {
      if (connection?.controller === controller) connection = null
      schedulePoll()
    }
  }

  function selectResearch(id) {
    const entry = history.value.find(item => item.id === id)
    if (!entry || entry.deleting) return
    if (activeId.value !== id) disconnect()
    activeId.value = id
    inputError.value = ''
    saveActive()
    void follow(entry)
  }

  async function loadJobs() {
    if (disposed) return
    if (syncing) { refreshRequested = true; return }
    syncing = true
    try {
      const response = await listResearchJobs()
      if (disposed) return
      const jobs = Array.isArray(response) ? response : response.jobs
      forgetRuns(Array.isArray(response.deleted_run_ids) ? response.deleted_run_ids : [])
      const latest = new Map()
      for (const job of jobs) if (!deletedRuns.has(job.run_id) && !latest.has(job.run_id)) latest.set(job.run_id, job)
      for (const job of [...latest.values()].reverse()) {
        let entry = history.value.find(item => item.runId === job.run_id)
        if (!entry && job.request_id && pendingRecord.value?.requestId === job.request_id) entry = pendingRecord.value
        if (entry && entry.jobCreatedAt > job.created_at) continue
        if (!entry) entry = reactive({ id: job.run_id, runId: job.run_id, jobId: '', report: '', reportSummary: '', tasks: [], cursor: 0, completedTasks: 0 })
        applySnapshot(entry, job)
      }
      void follow(activeResearch.value)
    } catch {
      storageNotice.value = '后台列表暂时不可用，请稍后刷新。'
    } finally {
      syncing = false
      if (refreshRequested && !disposed) {
        refreshRequested = false
        void loadJobs()
      } else schedulePoll()
    }
  }

  async function submitTopic() {
    if (sending.value) return
    const value = topic.value.trim()
    if (!value) { inputError.value = '请输入研究主题'; return }
    inputError.value = ''
    disconnect()
    const entry = createRecord(value)
    entry.requestId = globalThis.crypto.randomUUID()
    topic.value = ''
    try {
      applySnapshot(entry, await createResearchJob(value, entry.requestId))
      void follow(entry)
      schedulePoll()
    } catch (error) {
      if (!entry.jobId) {
        entry.status = 'interrupted'
        entry.message = error.message
      }
      await loadJobs()
    }
  }

  async function resumeTask() {
    if (sending.value) return
    const id = resumeId.value.trim()
    if (!RUN_ID.test(id)) { resumeError.value = '请输入正确的研究编号'; return }
    resumeError.value = ''
    disconnect()
    const entry = history.value.find(item => item.runId === id) ?? createRecord(`恢复研究 ${id}`, id)
    activeId.value = entry.id
    entry.status = 'submitting'
    try {
      applySnapshot(entry, await resumeResearchJob(id))
      entry.cursor = 0
      void follow(entry)
      schedulePoll()
    } catch (error) {
      entry.status = 'interrupted'
      entry.message = error.message
    }
  }

  async function stopActive() {
    const entry = activeResearch.value
    if (!entry?.jobId || entry.deleting || !['queued', 'running'].includes(entry.status)) return
    entry.status = 'stopping'
    entry.message = '正在停止全部研究分支……'
    try { applySnapshot(entry, await stopResearchJob(entry.jobId)) }
    catch (error) {
      entry.message = error.message
      // 后台是否停止以服务端状态为准，不能在请求失败时假装已停止。
      try { applySnapshot(entry, await getResearchJob(entry.jobId)) } catch { /* Polling will reconcile later. */ }
    }
    schedulePoll()
  }

  async function deleteResearch(id) {
    const entry = history.value.find(item => item.id === id)
    if (!entry?.runId || entry.deleting) return
    entry.deleting = true
    if (activeId.value === id) disconnect()
    try {
      await deleteResearchRun(entry.runId)
      forgetRuns([entry.runId])
    } catch (error) {
      await loadJobs()
      if (!deletedRuns.has(entry.runId)) storageNotice.value = `删除未确认：${error.message}`
    } finally {
      entry.deleting = false
      void follow(activeResearch.value)
      schedulePoll()
    }
  }

  function dispose() {
    disposed = true
    clearTimeout(pollTimer)
    disconnect()
    globalThis.removeEventListener?.('storage', onStorage)
  }

  return {
    topic, resumeId, inputError, resumeError, storageNotice, history,
    activeResearch, report, sending, newResearch, selectResearch, submitTopic, resumeTask,
    stopActive, deleteResearch, loadJobs, dispose,
  }
}
