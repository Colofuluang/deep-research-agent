
export async function previewResearch(topic) {
  const response = await fetch('/api/research/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  })

  if (!response.ok) {
    throw new Error(`请求失败：HTTP ${response.status}`)
  }

  return await response.json()
}

async function requestResearchStream(url, options, onEvent) {
  // 发送研究请求
  const response = await fetch(url, options)

  if (!response.ok) {
    throw new Error('研究请求失败：HTTP ' + response.status)
  }
  if (!response.body) {
    throw new Error('浏览器未提供响应流')
  }

  // 准备读取响应
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()

      if (done) {
        throw new Error('连接已结束，但未收到研究完成或失败事件')
      }

      buffer += decoder.decode(value, { stream: true })

      // 从暂存内容中取出完整事件
      let boundary = buffer.indexOf('\n\n')

      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)

        const lines = block.split('\n')
        const eventLine = lines.find((line) => line.startsWith('event:'))
        const dataLine = lines.find((line) => line.startsWith('data:'))

        if (dataLine) {
          const event = {
            event: eventLine ? eventLine.slice(6).trim() : 'message',
            data: JSON.parse(dataLine.slice(5).trim()),
          }

          // 把事件交给页面处理
          onEvent(event)

          if (event.event === 'completed' || event.event === 'error') {
            return
          }
        }

        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

export async function streamResearch(topic, onEvent) {
  return await requestResearchStream('/api/research/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ topic }),
  }, onEvent)
}

export async function resumeResearch(runId, onEvent) {
  return await requestResearchStream(
    '/api/research/' + encodeURIComponent(runId) + '/resume',
    {
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
    },
    onEvent,
  )
}