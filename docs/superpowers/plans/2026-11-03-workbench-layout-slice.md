# 研究工作台布局教学切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本次执行方式由用户明确指定为教学：用户编写页面，导师讲解、审查和验证，不代写项目源代码。

**Goal:** 将现有页面排成顶部标题、左侧操作与报告、右侧进度的工作台，并提供基础间距、颜色和窄屏适配。

**Architecture:** 保留 App.vue 的现有响应式状态、提交函数和事件处理函数，只重新组织模板。新增全局 style.css，由 main.js 导入。沿用现有 api.js，不增加依赖。

**Tech Stack:** Vue 3、JavaScript、CSS Grid/Flex、Vite。

**Spec:** ../specs/2026-11-03-research-workbench-design.md

## Global Constraints

- 用户编写核心代码，导师解释新概念、检查实现并验证。
- 继续使用 Vue 3、JavaScript、Vite 和已有 FastAPI/SSE 接口。
- 本切片不修改 script setup、api.js 或后端逻辑。
- 使用真实 topic、sending、message、runId、logs、report、resumeId；不填充示例报告或来源。
- Markdown 渲染、空闲/运行状态切换和独立来源预览由后续切片完成。

## Review Focus

1. 窄屏宽度不足：左右列应上下排列，页面不横向溢出。
2. 长研究编号和日志：文字应换行，保留日志中的换行符。
3. 超长报告：报告应在主列内换行，不撑宽 Grid。
4. 请求执行中：保留两表单原有 disabled 和防重复提交行为。
5. 无报告或无日志：显示明确的空状态，不伪造进度或成果。

## Task 1: 工作台骨架与基础样式

**Files:**
- Modify: frontend/src/App.vue（仅 template）
- Modify: frontend/src/main.js（增加一次样式导入）
- Create: frontend/src/style.css

**Interfaces:**
- Consumes: 原有 submitTopic()、resumeTask()、topic、message、sending、runId、logs、report、resumeId。
- Produces: `.app-shell`、`.app-header`、`.workspace`、`.workspace-main`、`.panel`、`.report-panel`、`.progress-panel` 等可复用布局类。
- 两表单仍分别通过 @submit.prevent 调用 submitTopic/resumeTask，保留 v-model 与 disabled 表达式。

- [ ] 先记录现有页面布局；确认状态和请求逻辑已正常运行。
- [ ] 在 App.vue 中组成顶部 header、左侧 section、右侧 aside；表单放左侧，编号、状态和日志放右侧；报告仍用 pre 显示。
- [ ] 新增 style.css：全局字体/盒模型，1180px 最大内容宽度，左右列 minmax(0, 1fr) 与 280px，24px 间距；800px 以下单列；长文本与报告允许换行。
- [ ] 在 main.js 中增加 import './style.css'。
- [ ] 构建验证：在 frontend 目录运行 npm run build，预期退出码为 0。
- [ ] 浏览器确认：宽屏有两列；缩窄窗口后单列；长编号、带换行日志和长报告不撑宽页面。
- [ ] 行为回归：空主题/空编号禁用提交；请求中禁用操作；恢复已完成研究后报告在左、真实进度在右。
- [ ] 用户提交实现后，导师检查；通过后进入下一教学切片。

## Self-review

- 已覆盖本切片的布局、基本排版、空状态和响应式目标。
- 设计说明中的按需展开恢复入口、完整状态外观与 Markdown 渲染明确留到后续，不宣称本切片完成整份设计。
- App.vue 的状态和函数名与当前保存版本一致。
- Review Focus 的五类情况均有浏览器或行为验收步骤。
- 本切片为可逆样式与模板调整，不安装新测试框架或编写映射 CSS 实现的断言测试。
