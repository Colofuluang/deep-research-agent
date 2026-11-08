<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useResearch } from './useResearch.js'
import { renderMarkdown } from './markdown.js'

const research = useResearch()
const {
  topic, resumeId, inputError, resumeError, storageNotice,
  history, activeResearch, report, sending,
} = research
const reportOpen = ref(false)
watch(() => activeResearch.value?.id, () => { reportOpen.value = false })
const sidebarOpen = ref(false)
const reportBack = ref(null)
const reportLaunch = ref(null)
const composerInput = ref(null)
const sidebarElement = ref(null)
const sidebarToggle = ref(null)
const sidebarClose = ref(null)
const reportHtml = computed(() => renderMarkdown(report.value))
const summaryHtml = computed(() => renderMarkdown(activeResearch.value?.reportSummary ?? ''))
const completedCount = computed(() => activeResearch.value?.tasks.filter((task) => task.status === 'completed').length ?? 0)
const statusLabels = { submitting: '正在提交', queued: '排队中', waiting: '等待执行', running: '执行中', stopping: '停止中', stopped: '已停止', completed: '已完成', failed: '执行失败', interrupted: '已中断' }
const progressLabel = computed(() => ({ queued: '等待后台执行', running: '研究进行中', stopping: '正在停止研究', stopped: '研究已停止', completed: '研究已完成' })[activeResearch.value?.status] ?? '研究已中断')
const composerAction = computed(() => {
  const entry = activeResearch.value
  if (entry?.status === 'submitting') return 'submitting'
  if (entry?.status === 'stopping') return 'stopping'
  if (entry?.jobId && ['queued', 'running'].includes(entry.status)) return 'stop'
  if (entry?.runId && (['stopped', 'interrupted', 'failed'].includes(entry.status) || (entry.status === 'completed' && !report.value))) return 'resume'
  return 'send'
})
const composerLabel = computed(() => ({
  send: '开始研究', stop: '停止研究', stopping: '正在停止研究', submitting: '正在提交研究',
  resume: activeResearch.value?.status === 'completed' ? '读取报告' : '恢复研究',
})[composerAction.value])
const composerDisabled = computed(() => activeResearch.value?.deleting || (composerAction.value === 'send'
  ? sending.value || !topic.value.trim() : ['submitting', 'stopping'].includes(composerAction.value)))
const composerHint = computed(() => composerAction.value === 'resume'
  ? `点击右侧三角${activeResearch.value?.status === 'completed' ? '读取报告' : '继续研究'}，或新建研究`
  : sending.value ? '任务在后台执行，可新建研究或切换其他记录'
    : activeResearch.value ? '发送新主题将创建另一项研究' : 'Enter 开始研究 · Shift + Enter 换行')
let conversationScroll = 0

function scrollTo(top) {
  if (typeof window !== 'undefined') window.scrollTo({ top, behavior: 'auto' })
}

function openSidebar() {
  sidebarOpen.value = true
  nextTick(() => sidebarClose.value?.focus())
}

function closeSidebar() {
  const wasOpen = sidebarOpen.value
  sidebarOpen.value = false
  if (wasOpen) nextTick(() => sidebarToggle.value?.focus())
}

function onSidebarTab(event) {
  if (!sidebarOpen.value) return
  const controls = [...sidebarElement.value.querySelectorAll('button:not([disabled]), input:not([disabled]), summary')]
    // Closed details can retain layout rectangles for inputs that cannot receive focus.
    .filter((element) => element.checkVisibility
      ? element.checkVisibility()
      : element.getClientRects().length && (element.tagName === 'SUMMARY' || !element.closest('details:not([open])')))
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

let mobileQuery
const onViewportChange = (event) => { if (!event.matches) closeSidebar() }
const onWindowFocus = () => { void research.loadJobs() }
onMounted(() => {
  mobileQuery = window.matchMedia('(max-width: 760px)')
  mobileQuery.addEventListener('change', onViewportChange)
  window.addEventListener('focus', onWindowFocus)
  void research.loadJobs()
})
onUnmounted(() => {
  mobileQuery?.removeEventListener('change', onViewportChange)
  window.removeEventListener('focus', onWindowFocus)
  research.dispose()
})

function newResearch() {
  research.newResearch()
  reportOpen.value = false
  closeSidebar()
  scrollTo(0)
  nextTick(() => composerInput.value?.focus())
}

function selectResearch(id) {
  research.selectResearch(id)
  reportOpen.value = false
  closeSidebar()
  scrollTo(0)
}

function openReport() {
  if (!report.value) return
  conversationScroll = typeof window === 'undefined' ? 0 : window.scrollY
  reportOpen.value = true
  nextTick(() => {
    scrollTo(0)
    reportBack.value?.focus({ preventScroll: true })
  })
}

function closeReport() {
  reportOpen.value = false
  nextTick(() => {
    scrollTo(conversationScroll)
    reportLaunch.value?.focus({ preventScroll: true })
  })
}

async function submitTopic() {
  if (composerAction.value !== 'send') return
  reportOpen.value = false
  await research.submitTopic()
}

async function resumeTask() {
  reportOpen.value = false
  const pending = research.resumeTask()
  if (!resumeError.value) closeSidebar()
  await pending
}

function resumeActive() {
  resumeId.value = activeResearch.value.runId
  return resumeTask()
}

function onComposerAction() {
  if (composerAction.value === 'stop') return research.stopActive()
  if (composerAction.value === 'resume') return resumeActive()
}

function onComposerEnter(event) {
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  return submitTopic()
}
</script>

<template>
  <div class="app-shell" @keydown.esc.prevent="closeSidebar">
    <button v-if="sidebarOpen" class="sidebar-backdrop" type="button" tabindex="-1" aria-label="关闭研究记录" @click="closeSidebar"></button>
    <aside id="research-sidebar" ref="sidebarElement" class="sidebar" :class="{ 'sidebar-open': sidebarOpen }" :role="sidebarOpen ? 'dialog' : undefined" :aria-modal="sidebarOpen ? 'true' : undefined" aria-label="研究记录" @keydown.tab="onSidebarTab">
      <div class="sidebar-brand">
        <span class="brand-mark" aria-hidden="true">◈</span>
        <span>深度研究助手</span>
        <button ref="sidebarClose" class="icon-button mobile-only" type="button" aria-label="关闭研究记录" @click="closeSidebar">×</button>
      </div>
      <button class="new-research-button" type="button" @click="newResearch">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        新建研究
      </button>
      <nav class="history-nav" aria-label="最近研究">
        <h2 class="sidebar-label">最近研究</h2>
        <p v-if="!history.length" class="history-empty">发起研究后，记录会显示在这里。</p>
        <div v-for="item in history" :key="item.id" class="history-row" :class="{ 'history-item-active': activeResearch?.id === item.id }">
          <button
          class="history-item"
          :aria-current="activeResearch?.id === item.id ? 'page' : undefined"
          :title="item.topic"
          :disabled="item.deleting"
          type="button"
          @click="selectResearch(item.id)"
        >
          <span class="history-title">{{ item.topic }}</span>
          <span class="history-state" :class="`history-state-${item.status}`">{{ statusLabels[item.status] }}</span>
          </button>
          <button class="history-delete" type="button" :disabled="item.deleting" :aria-label="`删除记录：${item.topic}`" :title="item.deleting ? '正在删除' : '删除记录'" @click="research.deleteResearch(item.id)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5" /></svg>
          </button>
        </div>
      </nav>
      <div class="sidebar-footer">
        <p v-if="storageNotice" class="storage-notice" role="status">{{ storageNotice }}</p>
        <p class="local-note">研究保存在后台，当前浏览器保留缓存</p>
      </div>
    </aside>

    <main class="workspace" :inert="sidebarOpen || undefined">
      <header class="workspace-header">
        <div class="header-heading">
          <button ref="sidebarToggle" class="icon-button mobile-only" type="button" aria-label="打开研究记录" aria-controls="research-sidebar" :aria-expanded="sidebarOpen" @click="openSidebar">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
          </button>
          <h1 :title="activeResearch?.topic">{{ activeResearch?.topic || '新建研究' }}</h1>
        </div>
        <span class="header-status" :class="{ 'is-running': activeResearch?.status === 'running' }">
          {{ reportOpen ? '报告阅读' : activeResearch ? statusLabels[activeResearch.status] : '研究工作台' }}
        </span>
      </header>

      <section v-if="reportOpen && report" id="report-reader" class="reader-view" aria-label="完整研究报告">
        <div class="reader-toolbar">
          <button ref="reportBack" class="text-button" type="button" @click="closeReport">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 5-7 7 7 7M5 12h14" /></svg>
            返回对话
          </button>
          <span>完整研究报告</span>
        </div>
        <article class="report-content" v-html="reportHtml"></article>
      </section>

      <template v-else>
        <section v-if="!activeResearch" class="welcome" aria-label="开始新的研究">
          <div class="welcome-mark" aria-hidden="true">◈</div>
          <p class="eyebrow">DEEP RESEARCH</p>
          <h2>今天想深入研究什么？</h2>
          <p>从一个问题开始，整理一份有来源的研究报告。</p>
        </section>

        <section v-else class="conversation-column" aria-label="研究对话">
          <div class="user-message">{{ activeResearch.topic }}</div>
          <article class="assistant-message">
            <div class="assistant-label"><span aria-hidden="true">◈</span>研究助手</div>
            <details v-if="activeResearch.tasks.length" :key="activeResearch.id" class="research-progress">
              <summary>
                <span class="progress-dot" :class="`progress-dot-${activeResearch.status}`" aria-hidden="true"></span>
                {{ progressLabel }}
                <span class="progress-count">{{ completedCount }} / {{ activeResearch.tasks.length }} 项任务</span>
              </summary>
              <ol class="task-list">
                <li v-for="task in activeResearch.tasks" :key="task.number" class="task-row">
                  <span class="task-status" :class="`task-status-${task.status}`">{{ statusLabels[task.status] }}</span>
                  <div><h3>{{ task.title }}</h3><p>{{ task.latestMessage }}</p></div>
                </li>
              </ol>
            </details>
            <p v-if="['submitting', 'queued', 'running', 'stopping', 'stopped'].includes(activeResearch.status)" class="execution-message" role="status">{{ activeResearch.message }}</p>
            <template v-if="report">
              <template v-if="summaryHtml">
                <p class="summary-label">核心结论</p>
                <div class="report-content report-summary" v-html="summaryHtml"></div>
              </template>
              <p v-else class="execution-message">研究报告已生成，可打开完整报告查看结论与参考来源。</p>
              <button ref="reportLaunch" class="report-card" type="button" aria-controls="report-reader" @click="openReport">
                <span class="report-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg></span>
                <span class="report-card-text"><strong>{{ activeResearch.topic }}</strong><span>阅读完整报告 · 含参考来源</span></span>
                <svg class="report-card-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10" /></svg>
              </button>
            </template>
            <p v-else-if="activeResearch.status === 'completed'" class="execution-message">研究已完成，点击右下角三角读取报告。</p>
            <p v-if="['interrupted', 'failed'].includes(activeResearch.status)" class="error-text" role="alert">{{ activeResearch.message }}</p>
            <details v-if="activeResearch.runId" class="run-id-details">
              <summary>研究编号</summary>
              <code>{{ activeResearch.runId }}</code>
            </details>
          </article>
        </section>

        <footer class="composer-wrap">
          <form class="composer" @submit.prevent="submitTopic">
            <label class="sr-only" for="research-topic">研究主题</label>
            <textarea
              id="research-topic"
              ref="composerInput"
              v-model="topic"
              :disabled="sending || composerAction === 'resume'"
              :placeholder="composerAction === 'resume' ? '点击右侧三角继续，或新建研究…' : activeResearch ? '输入新主题，开始另一项研究…' : '描述你想研究的问题…'"
              rows="2"
              @keydown.enter.exact="onComposerEnter"
            ></textarea>
            <div class="composer-actions">
              <span class="composer-mode"><span aria-hidden="true">◈</span>深度研究</span>
              <button class="send-button" :type="composerAction === 'send' ? 'submit' : 'button'" :disabled="composerDisabled" :aria-label="composerLabel" :title="composerLabel" @click="onComposerAction">
                <svg v-if="['stop', 'stopping', 'submitting'].includes(composerAction)" class="stop-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" /></svg>
                <svg v-else-if="composerAction === 'resume'" class="resume-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 11 7-11 7z" fill="currentColor" stroke="none" /></svg>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
              </button>
            </div>
          </form>
          <p v-if="inputError" class="composer-error error-text" role="alert">{{ inputError }}</p>
          <p class="composer-hint">{{ composerHint }}</p>
        </footer>
      </template>
    </main>
  </div>
</template>
