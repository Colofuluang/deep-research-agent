# HelloAgents 第十四章阅读与迁移记录

阅读日期：2026-10-31。依据当前工作区本地文件，不把本地快照声称为上游最新版本。

## 阅读范围

- docs/chapter14/第十四章 自动化深度研究智能体.md 全文 2152 行。
- docs/images/14-figures/ 中十张图与两张表：架构、请求流转、任务流程、工具调用、搜索调度、前端布局与 SSE。
- 配套 backend/src：agent.py、main.py、config.py、models.py、prompts.py、utils.py、包入口。
- 全部 backend/src/services：planner、search、summarizer、reporter、notes、tool_events、text_processing 与包入口。
- frontend/src/App.vue 的模板、脚本和样式；services/api.ts、入口、环境类型与样式；package.json、Vite、TypeScript 和 HTML 配置。
- 后端 pyproject.toml 与示例配置中的非密钥设置。
- 当前 deep-research 项目的实现进度与已安装关键依赖。

未读取用户真实 .env 的密钥，也没有调用用户的模型、搜索服务或运行完整参考项目。

## 一次请求在实际代码中的路径

1. 前端提交 topic 与可选的 search_api。
2. services/api.ts 使用 fetch 发起 POST /research/stream，逐段解析 data: JSON 事件。
3. 后端 main.py 构造 Configuration 和 DeepResearchAgent，以 StreamingResponse 返回事件。
4. agent.py 创建本次 SummaryState，调用 PlanningService 得到 TodoItem 列表；空计划使用一个后备任务。
5. 流式路径为每个任务创建工作线程；每个线程执行搜索、上下文整理、总结。
6. services/search.py 调用框架 SearchTool，传入指定 backend、structured 模式、max_results=5 和正文相关配置。
7. utils.py 按 URL 去重，把 content 与可选 raw_content 格式化为模型输入，正文按字符近似限制长度。
8. SummarizationService 为每个任务创建独立 Agent；提示词包含整体主题、任务意图、查询、资料和笔记指引。
9. ToolCallTracker 记录工具事件，推断 task_id 与 note_id，并将笔记信息同步到任务记录。
10. 收齐任务事件后，ReportingService 根据任务状态、总结、来源和笔记引用生成报告。
11. 协调器显式保存最终报告，推送 final_report 与 done。
12. 前端按 task_id 更新任务、来源、总结、笔记和工具日志，展示最终报告。

## 实际能力与边界

### 三种角色与调用方式

规划、总结和报告是不同职责的模型调用。搜索由协调层调用，不要求模型每次自主选择搜索工具。

实际 agent.py 注册到 ToolRegistry 的主要是 NoteTool。规划、总结和报告的提示词要求模型创建、读取或更新笔记；ToolAwareSimpleAgent 的监听器和 ToolCallTracker 用于记录这些动作。

迁移时可以先把应当发生的保存操作交给确定性代码，再专门教学模型如何自主调用笔记工具。这样仍保留笔记协作的学习目标，也能清楚区分两种控制方式。

### 搜索

实际默认配置和 .env.example 都使用 duckduckgo。配置枚举还包括 tavily、perplexity、searxng、advanced。

SearchTool 在框架包内，项目代码负责传参、提取结果和整理上下文。结构化结果包括 results、backend、answer、notices。实际上下文整理使用 content 和 raw_content，而文档部分简化示例使用 snippet。

后端依赖声明为 hello-agents==0.2.9；当前 Conda 环境中的 hello-agents 是 0.2.2。因此本记录不把当前旧包的底层实现当成参考项目所锁定版本的完整实现。新项目直接用 LangGraph 和搜索服务适配，不依赖 HelloAgents。

### 文档示例与实际代码不完全相同

| 文档中的讲解或设想 | 配套代码实际行为 | 教学处理 |
| --- | --- | --- |
| 顺序协作、逐任务执行 | run_stream 创建线程并发执行任务 | 先顺序理解状态，再学习 Send 并发 |
| 简化的 SearchService 类 | 实际采用 dispatch_search 与 prepare_research_context 函数 | 学职责，不机械复制类名 |
| EventSource 示例 | 实际前端用 fetch POST /research/stream 解析 SSE | 使用可互通的实际请求方式 |
| Markdown 渲染示例 | 当前 App.vue 用 pre 显示报告和总结，package.json 未引入 marked | 产品阶段单独实现并验证渲染 |
| 记笔记支持恢复的目标 | 笔记读写已实现，但未找到按运行 ID 自动恢复整个流程的入口 | 把 checkpoint 恢复作为独立能力验证 |
| 多轮研究与最大轮数配置 | 配置存在，但协调器未用它控制按缺口重新搜索的循环 | 自主补充研究单独设计条件边和预算 |
| 搜索缓存的扩展示例 | 配套服务层没有实现该示例中的本地缓存类 | 按实际需求安排，不声称已具备 |

### 同步入口中的生成器问题

agent.py 的 _execute_task 中有 yield，所以即使传入 emit_stream=False，调用结果仍是生成器。

同步 run 在第 136 行仅调用 _execute_task(...)，没有消费生成器；任务函数体因此不会在这个调用点执行。流式路径通过 for 消费，行为不同。

已将该方法从源码中单独提取做离线检查：调用但不迭代，任务状态保持 pending。该检查不需要真实模型、工具或框架 Agent 初始化，也没有运行参考项目的完整请求。

迁移时统一在 LangGraph 节点中实现业务逻辑，由 invoke 或 stream 驱动同一张图，避免为同步与流式各维护一套任务执行路径。

## 数据契约与迁移原则

- ResearchTask 表示任务定义，任务执行成果单独记录状态、资料、总结与失败原因。
- State 是运行过程中的共享数据；模型每轮只接收相关字段。
- 默认状态更新会覆盖旧值。累积、重试、并行合并时再明确 reducer，不盲目复制 operator.add。
- URL、来源编号、引用支持关系由程序和证据记录维护，不让报告模型自行重新发明来源。
- 笔记是研究工件，checkpoint 是执行快照，二者都不能代替事实核验。
- 先完成可解释的工作流，再加入模型决定补充检索的循环。
- 图编排、搜索适配、API 与前端分开验证。

## 本次已验证与未验证

已验证：完整本地文档与配套代码阅读；生成器行为的隔离检查；当前 LangGraph 版本下的三任务条件循环、报告生成和节点更新流的离线实验。

未验证：参考项目在其锁定依赖下的完整启动与服务调用；新项目真实 LangGraph 研究链路；Tavily 账号密钥、搜索质量和全文读取；前端浏览器运行。不能把文档中的能力描述或离线固定数据实验当成这些功能已经验收。
