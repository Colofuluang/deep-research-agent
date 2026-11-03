<script setup>
import { ref } from 'vue'
import { streamResearch, resumeResearch } from './api.js'

const topic = ref('')
const message = ref('')
const sending = ref(false)
const runId = ref('')
const logs = ref([])
const report = ref('')
const resumeId = ref('')

function handleResearchEvent(event) {
    const data = event.data

    if (event.event === 'started') {
      runId.value = data.run_id
      resumeId.value = data.run_id
      topic.value = data.topic
      message.value = data.mode === 'resume'
        ? '正在恢复研究'
        : '研究已启动'
    } else if (event.event === 'progress') {
        logs.value.push(data.message)
    } else if (event.event === 'completed') {
        report.value = data.report
        message.value = '研究已完成'
    } else if (event.event === 'error') {
        message.value = '研究失败：' + data.message
    }
}



async function submitTopic() {
  if (sending.value) return

  const value = topic.value.trim()
  if (!value) {
    message.value = '请输入研究主题'
    return
  }

  sending.value = true
  message.value = ''
  runId.value = ''
  logs.value = []
  report.value = ''

  try {
    await streamResearch(value, handleResearchEvent)
  } catch (error) {
    message.value = '研究中断：' + error.message
  } finally {
    sending.value = false
  }
}

async function resumeTask() {
  if (sending.value) return

  const id = resumeId.value.trim()
  if (!id) {
    message.value = '请输入研究编号'
    return
  }

  if (!/^[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$/.test(id)) {
    message.value = '研究编号格式不正确'
    return
  }

  sending.value = true
  message.value = '正在恢复研究……'
  runId.value = ''
  logs.value = []
  report.value = ''

  try {
    await resumeResearch(id, handleResearchEvent)
  } catch (error) {
    message.value = '恢复失败：' + error.message
  } finally {
    sending.value = false
  }
}
</script>
<template>
  <div class="app-shell">
    <header class="app-header">
      <div>
        <p class="eyebrow">RESEARCH WORKSPACE</p>
        <h1>深度研究助手</h1>
      </div>
      <span class="app-label">研究工作台</span>
    </header>

    <main class="workspace">
      <section class="workspace-main" aria-label="研究操作与报告">
        <section class="panel">
          <h2>你想深入研究什么？</h2>
          <p class="muted">从一个问题开始，整理一份有来源的研究报告。</p>

          <form class="form-stack" @submit.prevent="submitTopic">
            <label for="topic">研究主题</label>
            <textarea
              id="topic"
              v-model="topic"
              :disabled="sending"
              placeholder="描述你想研究的问题……"
              rows="4"
            ></textarea>
            <button type="submit" :disabled="sending || !topic.trim()">
              {{ sending ? '研究中……' : '开始研究' }}
            </button>
          </form>

          <form class="form-stack restore-form" @submit.prevent="resumeTask">
            <label for="resume-id">恢复已有研究</label>
            <input
              id="resume-id"
              v-model="resumeId"
              :disabled="sending"
              placeholder="输入研究编号"
            />
            <button
              class="secondary-button"
              type="submit"
              :disabled="sending || !resumeId.trim()"
            >
              恢复研究
            </button>
          </form>
        </section>

        <article class="panel report-panel">
          <h2>研究报告</h2>
          <pre v-if="report" class="report-text">{{ report }}</pre>
          <p v-else class="muted">完成研究后，报告会显示在这里。</p>
        </article>
      </section>

      <aside class="panel progress-panel" aria-label="研究进度">
        <h2>研究进度</h2>
        <p class="status-text" role="status">{{ message || '等待开始研究' }}</p>
        <p v-if="runId" class="run-id">研究编号：{{ runId }}</p>

        <ul v-if="logs.length" class="progress-log">
          <li v-for="(log, index) in logs" :key="index">{{ log }}</li>
        </ul>
        <p v-else class="muted">研究开始后，执行进度会在这里更新。</p>
      </aside>
    </main>
  </div>
</template>