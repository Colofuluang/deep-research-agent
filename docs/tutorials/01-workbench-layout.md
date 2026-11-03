# 第一个界面切片：搭建研究工作台布局

这一节由你修改三个前端文件。导师已在临时目录验证示例能构建，项目中的页面源文件没有被代改。

目标：将原有单列页面排为顶部标题、左侧研究操作与报告、右侧进度。先建立布局与基础样式；居中空闲首页、顶部展开恢复、完整状态外观和 Markdown 渲染在后续切片继续完善。

## 先理解三个层次

- HTML/模板决定页面有哪些区域，以及哪个区域包含哪些内容。
- CSS 决定区域如何排列、尺寸、颜色和间距。
- Vue 的 script setup 保存状态并处理请求。本节保留你现有的这部分代码。

class 是给元素贴上的样式标签。例如 class="workspace" 对应 CSS 中的 .workspace；这里的 class 与 Python 的类定义没有关系。

结构如下：

```text
app-shell
├── app-header
└── workspace（Grid 容器）
    ├── workspace-main（左列）
    │   ├── 研究和恢复表单
    │   └── 报告区域
    └── progress-panel（右列）
        └── 状态、编号和进度日志
```

## 第一步：整理 App.vue 的模板

文件：frontend/src/App.vue。

完整保留 <script setup> 到 </script>。只把现有 <template> 到 </template> 替换为下列内容。

这里继续使用你写好的 topic、sending、resumeId、runId、logs、report、message，以及 submitTopic()/resumeTask()。

研究主题的 input 改为 textarea，便于输入较长的问题；v-model 和请求逻辑沿用原来的写法。

```vue
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
```

标签的语义：

- header：页面顶部。
- main：页面的主要内容。
- section：按主题组织的一块内容。
- article：可独立阅读的报告。
- aside：与主内容有关的辅助信息，这里放研究进度。

这些标签本身不会自动组成左右布局，排列由下一步的 CSS 控制。

## 第二步：创建 style.css

文件：frontend/src/style.css。

CSS 规则的基本形式：

```css
.workspace {
  display: grid;
}
```

.workspace 是选择器，表示找到 class 包含 workspace 的元素；花括号中是作用于它的样式声明。

将以下完整内容写入 style.css：

```css
:root {
  color-scheme: light dark;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
  line-height: 1.6;
  --page-bg: light-dark(#f5f7f5, #151a19);
  --panel-bg: light-dark(#ffffff, #1b211f);
  --text: light-dark(#223028, #e8efeb);
  --muted: light-dark(#65756b, #a3b1a9);
  --border: light-dark(#dce5df, #354039);
  --accent: light-dark(#286149, #a0d5b7);
  --on-accent: light-dark(#ffffff, #14281c);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page-bg); color: var(--text); }
button, input, textarea { font: inherit; }
h1, h2, p { margin: 0; }
h1 { font-size: 25px; font-weight: 500; }
h2 { font-size: 19px; font-weight: 500; margin-bottom: 12px; }

.app-shell { max-width: 1180px; margin: 0 auto; padding: 32px 24px; }
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}
.eyebrow { color: var(--accent); font-size: 11px; letter-spacing: 1.5px; }
.app-label, .muted { color: var(--muted); font-size: 13px; }

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 24px;
  align-items: start;
}
.workspace-main { display: grid; gap: 24px; min-width: 0; }
.panel {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel-bg);
}
.form-stack { display: grid; gap: 12px; margin-top: 22px; }
.form-stack label { font-size: 13px; }
input, textarea {
  width: 100%;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--page-bg);
  color: var(--text);
}
textarea { resize: vertical; }
button {
  justify-self: start;
  padding: 10px 18px;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  cursor: pointer;
}
button:disabled { opacity: .5; cursor: not-allowed; }
.secondary-button { background: transparent; color: var(--accent); }
.restore-form { border-top: 1px solid var(--border); padding-top: 22px; }
.status-text { color: var(--accent); margin-top: 16px; }
.run-id { color: var(--muted); font-size: 12px; margin-top: 12px; overflow-wrap: anywhere; }
.progress-log { margin: 18px 0 0; padding-left: 18px; }
.progress-log li { padding: 8px 0; white-space: pre-line; overflow-wrap: anywhere; }
.report-text { font: inherit; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }

@media (max-width: 800px) {
  .workspace { grid-template-columns: 1fr; }
  .app-shell { padding: 20px 16px; }
}

```

### 优先读懂布局的这四行

```css
display: grid;
grid-template-columns: minmax(0, 1fr) 280px;
gap: 24px;
align-items: start;
```

- display: grid：将容器的直接子元素按网格排列；这里直接子元素是左侧 section 和右侧 aside。
- grid-template-columns：定义两列。右列占 280px；左列获得剩余空间。
- minmax(0, 1fr)：让左列能缩小，避免长文本把整列撑宽。1fr 在这里表示剩余可用空间的一份。
- gap：两列之间留出 24px。
- align-items: start：两列从顶部对齐，进度面板无需拉长到与整篇报告一样高。

参考：[MDN grid-template-columns](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/grid-template-columns)。

### 再区分 margin、padding 和 gap

- margin：元素外部的间距。
- padding：内容与元素边缘之间的内部留白。
- gap：Grid/Flex 容器中子元素之间的间距。

.panel 的 padding: 24px 让文字与面板边缘保持距离；.app-header 的 margin-bottom: 28px 让顶部与下面的工作区分开。

box-sizing: border-box 让声明的宽度包含边框和内边距，便于控制页面尺寸。参考：[MDN box-sizing](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/box-sizing)。

### 颜色与字体先作为统一配置阅读

:root 中 -- 开头的名称是 CSS 自定义属性，可通过 var(...) 在其他规则中复用。

light-dark(浅色值, 深色值) 配合 color-scheme: light dark，让配色跟随浏览器的外观偏好。它不参与研究请求。

font-family 是依次尝试的字体列表；border-radius 是圆角大小。暂时不必逐个背下这些数值。

### 最后理解窄屏规则

```css
@media (max-width: 800px) {
  .workspace { grid-template-columns: 1fr; }
}
```

窗口宽度不超过 800px 时，这条规则将两列改成一列。左侧操作/报告在上，进度在下。

报告的 white-space: pre-wrap 保留换行并允许自动换行；overflow-wrap: anywhere 帮助较长的编号、URL 或文本在窄屏内换行。

## 第三步：让入口加载样式

文件：frontend/src/main.js。

```javascript
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
```

import './style.css' 表示加载这份样式。没有这一行，仅创建 CSS 文件不会让页面采用这些规则。

## 第四步：验证

1. 保存三个文件，保持原来的 npm run dev 运行，或在 frontend 目录启动它。
2. 打开页面：桌面宽度应显示左右两列。
3. 缩窄浏览器窗口：不超过 800px 后应改为上下排列。
4. 输入一个已经完成的研究编号并恢复：报告应在左侧，编号和真实日志在右侧。无进度事件时显示空状态是正常的。
5. 确认空主题/空编号依旧禁用提交，请求中两组操作均被禁用。
6. 在 frontend 目录执行 npm run build，预期退出码为 0。

本切片仍把报告当文本展示，Markdown 标题暂时可能保留 # 等标记；下一阅读排版切片再处理 Markdown。

## 小练习

把 grid-template-columns 中的 280px 临时改为 320px，观察右栏变宽、左栏变窄，再改回 280px。

用你自己的话解释：为什么只改这一个值，两列宽度就一起发生变化？理解后再继续下一片，而不是逐行记忆 CSS。

