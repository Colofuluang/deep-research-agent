# 第一版作品集发布指南

本文针对当前 deep-research 项目。此时项目尚未初始化 Git；发布前应先整理文件和文档。本文是教程，不代表已经创建或发布 GitHub 仓库。

## 1. 发布根目录

只发布 deep-research 这个目录。不要在外层「AI Agent开发」目录初始化仓库，否则可能把 HelloAgents 参考仓库等无关内容一起纳入。

```bash
cd "/Volumes/LaCie/AI Agent开发/deep-research"
```

## 2. 哪些文件上传

| 内容 | 处理 |
| --- | --- |
| src/deep_research/ 下的 Python 源码 | 上传 |
| frontend/src/、index.html、vite.config.js | 上传真正使用的页面和配置 |
| pyproject.toml | 上传，先补直接依赖 |
| frontend/package.json、frontend/package-lock.json | 都上传，lockfile 用于确定前端安装版本 |
| README.md、.gitignore、.env.example | 上传；.env.example 只能放空值或说明性占位 |
| 架构说明、公开截图、精选演示报告 | 上传，先核对内容适合公开 |
| docs 中的学习笔记和设计记录 | 可保留；从 README 优先链接作品说明和运行指南 |
| .env、.venv/、node_modules/、__pycache__/ | 不上传 |
| outputs/、checkpoints.sqlite 等数据库 | 不上传 |
| *.egg-info/、dist/、build/、日志、._*、.DS_Store | 不上传 |
| 未使用的空组件占位文件 | 本次已清理；将来增加真正使用的组件时正常提交 |

本机 .env 保留用于运行；不上传不等于删除。普通研究输出可能包含用户主题、网页全文和运行状态，作品集应另外精选适合展示的材料，而不是公开整个 outputs。

## 3. 先完善 .gitignore

将项目根目录 .gitignore 写为：

```gitignore
# Credentials
.env
.env.*
!.env.example

# Python
.venv/
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/

# Frontend
node_modules/
dist/
build/

# Runtime research data
outputs/
*.sqlite
*.sqlite3
*.sqlite-*
*.sqlite3-*
*.db
*.db-*

# Local/editor files
.DS_Store
._*
.idea/
.vscode/
*.log

```

.env.* 规则后面的 !.env.example 是一个例外：真实环境配置应排除，示例配置可以上传。

.gitignore 只影响未跟踪文件。已经提交过的敏感文件不能仅靠新增忽略规则消除。本项目当前还没有 Git 仓库，所以先完善忽略规则再做第一次提交最直接。

参考：[GitHub 忽略文件说明](https://docs.github.com/en/get-started/git-basics/ignoring-files)。

## 4. 修正当前运行配置与依赖

### config.py

当前 config.py 已移除未使用的 SerpApi 必填检查，使用 DeepSeek 和 Tavily 配置。后续新增服务时，应同步更新配置读取、示例文件与 README。

### pyproject.toml

代码直接导入 requests、bs4、langchain_core，当前已把对应发行包列为直接依赖：

```toml
"requests",
"beautifulsoup4",
"langchain-core",
```

保留其他已使用的依赖。无需把整个 Conda 环境导出的所有包都作为项目直接依赖。

### .env.example

根目录 .env.example 已整理为不含真实密钥的模板：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
TAVILY_API_KEY=
```

使用者复制后填写自己的密钥：

```bash
cp .env.example .env
```

如果本地已经有正在使用的 .env，保留它；复制示例配置这一步用于新克隆的项目。模型名称按实际账号可访问的服务配置。

## 5. README 应该如何写

当前 README 已按实际功能重写，并移除了不存在的 examples/01_state_graph.py 路径。后续增加功能或调整启动方式时，同步更新对应说明。

推荐按下面顺序组织。

### 项目简介

可采用：

> 基于 LangGraph 的自动化研究工作流应用。输入研究主题后，系统生成任务计划，执行联网搜索、网页正文提取和任务总结，生成带来源编号的研究报告，并抽查关键结论的引用支持情况。应用提供 FastAPI 接口、SSE 实时进度、SQLite 检查点恢复和 Vue 页面。

### 演示

放真实运行截图，推荐包括：
- 首页或研究工作台；
- 研究执行进度；
- 最终报告；
- 失败后按研究编号恢复。

截图放到 docs/images/，使用 README 中的相对链接。截图前收起密钥、账号信息及无关个人内容。

另选一份适合公开的报告放在 docs/demo/report.md。保留原来的来源标注，注明生成日期和它只是展示样例，不能保证所有结论正确。不要把大批网页全文和 SQLite 检查点作为演示上传。

如果这些材料还没有准备好，先准备材料再添加对应链接，避免出现失效图片。

### 已实现能力

- LLM 生成结构化研究任务，Pydantic 验证。
- Tavily 搜索、网页正文提取及摘要回退。
- 多任务顺序执行、报告合成、来源编号检查。
- 最多抽查三条带引用结论的证据支持情况。
- 搜索超时后自动重试一次。
- SQLite 检查点，支持 CLI 和 HTTP 恢复。
- FastAPI + SSE + Vue 的进度和报告展示。
- JSON 研究记录、Markdown 报告和评估结果落盘。

### 架构

使用 Mermaid 或一张图说明：

```text
Vue 页面 → FastAPI → runner → LangGraph
                           ├─ DeepSeek
                           ├─ Tavily / 网页读取
                           ├─ SQLite 检查点
                           └─ outputs 中的研究成果
```

研究图的节点按代码如实列出：plan → search → fetch → summarize → record → persist → advance；任务结束后 report → extract → evaluate。

### 环境、安装和运行

记录经过你实际验证的环境，例如 Python 3.11、Node.js 24。本机开发环境使用 Conda，公开教程可以以此作为一种运行方式。

后端，在项目根目录：

```bash
conda create -n deep-research python=3.11
conda activate deep-research
python -m pip install -e .
cp .env.example .env
```

填写 .env 后，在项目根目录启动：

```bash
PYTHONPATH=src python -m uvicorn deep_research.api:app --reload
```

另开终端，前端：

```bash
cd frontend
npm ci
npm run dev
```

说明后端 /docs 地址，以及浏览器访问 Vite 实际打印的 Local 地址。不要把本机硬盘绝对路径写成其他使用者必须存在的路径。

CLI 作为另一种使用方式，在项目根目录执行：

```bash
PYTHONPATH=src python -m deep_research.main
```

### 恢复方式和输出

说明页面的「恢复研究」和 CLI 的 resume 都需要原 run_id。检查点保存在 outputs/<run_id>/checkpoints.sqlite。

运行输出包含 research.json、report.md、evaluation.json。这些文件由使用者自行运行生成，仓库默认不提交。

说明模型和搜索服务需要使用者自己的 API 密钥与额度；上传源码不意味着提供免费在线研究服务。

### 已知边界

- 当前主要为模型规划、程序编排的研究工作流。
- 列出的信息缺口不会自动触发新一轮补充研究。
- 引用抽查不是整篇报告的事实核验。
- 正文处理与送入模型的材料存在长度限制。
- 网页可访问性和第三方服务会影响结果。
- 仓库展示的是本地运行方案；尚未完成的功能放到 Roadmap。

### 来源和贡献

明确写明参考 Datawhale HelloAgents 第十四章，并说明本项目使用 LangGraph 重新组织状态和执行流程。把自己实现或集成的检查点恢复、SSE、引用评估与前端交互等具体工作写清楚。

实际复用的代码、文档或图片需要按其授权处理，参见下一节。使用 AI 辅助开发可以说明，但更重要的是能够解释与维护提交的代码。

## 6. 许可证先核对复用范围

核对时发现，HelloAgents 根目录 LICENSE.txt 使用 CC BY-NC-SA 4.0，不能直接假设是 MIT。

- [HelloAgents 许可原文](https://github.com/datawhalechina/hello-agents/blob/main/LICENSE.txt)
- [Creative Commons 许可摘要](https://creativecommons.org/licenses/by-nc-sa/4.0/)
- [GitHub 关于仓库许可证的说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)

只参考实现思路，与直接复制代码、文档或图片，需要分别核对实际复用情况。不要在没有核对时，把整仓库统一标成 MIT。本次没有替你选择或添加 LICENSE，也没有认定你的全部代码必然适用某一许可。

## 7. 创建 GitHub 空仓库

在 GitHub 创建新仓库：
- 名称示例：deep-research-agent。
- 作为可被面试官访问的作品集时，可在完成内容与授权检查后选择 Public；未准备好时可先 Private。
- 创建空仓库，本地已有 README 和 .gitignore，本次创建时不要额外初始化 README、.gitignore 或 LICENSE。
- 保存 GitHub 显示的仓库 HTTPS 地址。

不需要把整个「AI Agent开发」目录上传，也不需要复制 hello-agents-main 参考仓库。

## 8. 本地初始化与第一次提交

下面步骤在完成前面的文件整理之后执行。

```bash
cd "/Volumes/LaCie/AI Agent开发/deep-research"
git init -b main
git status --short
git check-ignore -v .env frontend/node_modules/ outputs/ src/deep_research.egg-info/
git add --dry-run .
```

check-ignore 应能说明真实配置和运行产物被哪条规则忽略；dry-run 只预览将暂存的文件，不提交也不上传。确认列表中没有 .env、node_modules、outputs 和数据库后再继续：

```bash
git add .
git diff --cached --stat
git diff --cached --name-only
git commit -m "feat: initial deep research agent"
```

add 是把文件放入暂存区；commit 是记录本地版本；push 才会把提交发送到 GitHub。

如果提示作者身份未配置，在当前仓库设置自己的姓名与提交邮箱；可使用 GitHub 设置中提供的 noreply 邮箱。不要把文档里的占位姓名、邮箱当成真实配置。

## 9. 连接远程并上传

将 YOUR_USERNAME 和仓库名替换为自己的真实值：

```bash
git remote add origin https://github.com/YOUR_USERNAME/deep-research-agent.git
git remote -v
git push -u origin main
```

首次通过命令行连接可能需要身份认证。使用配置好的 GitHub 浏览器授权、凭据管理或 SSH；不要把登录密码、PAT 或私钥贴进聊天、源码或截图。

参考：[GitHub 本地代码上传教程](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)、[认证方式](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)。

此时上传的是源码，前后端不会因此自动成为在线服务。第一版作品集可先提供截图、演示与可复现的运行说明。

## 10. 上传后的最后验收

- 在 GitHub 检查 README 图片、相对链接、文件目录。
- 确认 .env、运行数据库和依赖目录没有出现在仓库中。
- 在另一个空目录克隆仓库，按 README 安装、填自己的配置并运行，记录真正有效的步骤。
- 未验证部署、并发、评估效果或性能的数据，不写成已实现成果。
- 一切正常后，可创建 v0.1.0 标签；之后的功能通过后续提交和版本继续迭代。

```bash
git tag v0.1.0
git push origin v0.1.0
```

## 11. 简历描述示例

> 基于 LangGraph 实现自动化研究工作流，集成 DeepSeek、Tavily 与网页正文提取，完成任务规划、资料总结和带来源引用的报告生成；使用 SQLite 检查点实现跨进程恢复，并通过 FastAPI、SSE 和 Vue 提供实时进度与报告展示，增加引用编号校验和关键结论证据抽查。

如果没有量化测试，不写「准确率提升 X%」「生产级高可用」「支持大规模并发」等结论。项目的技术边界、遇到的问题和真实解决方法，本身就是面试中可展开的内容。

## 当前检查结果与未执行事项

- 本地 Git 尚未初始化。
- 当前 .gitignore 已包含密钥、前后端依赖、研究输出、安装产物和系统辅助文件的忽略规则。
- 四个未使用的空组件占位文件已清理。
- .env.example 已重置为空密钥模板，实际 .env 保持原样。
- package-lock.json 存在，应提交。
- 候选文本源码中进行了一次有限的硬编码凭据模式检查，未检出匹配；这不是全面的秘密扫描，也未读取 .env。
- 已更新 README 与截图说明；本次未改动业务逻辑，未初始化 Git、创建远程仓库、提交或推送。

