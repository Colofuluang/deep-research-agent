import json
import logging
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer

from .citations import extract_citation_ids, find_invalid_citations
from .evaluation import check_claims, extract_claims
from .llm import create_llm, invoke_llm
from .models import (
    ResearchPlan,
    ResearchTask,
    SearchResult,
    SourceSelection,
    TaskResearch,
    TaskMaterials,
)
from .prompts import (
    PLANNER_SYSTEM_PROMPT,
    REPORTER_SYSTEM_PROMPT,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    SOURCE_SELECTOR_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    CONCLUSION_DISTILLER_SYSTEM_PROMPT,
)
from .selection import build_report_materials, select_task_sources
from .state import ResearchState, TaskState
from .storage import save_report_materials, save_research_records, save_task_record
from .tools.definitions import (
    MAX_TOOL_ROUNDS,
    MAX_TOOLS_PER_ROUND,
    RESEARCH_TOOLS,
)
from .tools.fetch import assess_page_content, fetch_web
from .tools.search import search_web

logger = logging.getLogger(__name__)


def prepare_task_node(state: TaskState) -> dict:
    task = state["task"]

    return {
        "messages": [
            HumanMessage(
                content=(
                    f"研究任务：{task.title}\n"
                    f"研究目的：{task.intent}\n"
                    f"初始搜索建议：{task.query}\n\n"
                    "请收集完成本任务所需的外部资料。"
                )
            )
        ],
        "tool_rounds": 0,
        "current_results": [],
    }


def decide_task_node(state: TaskState) -> dict:
    task_number = state["task_number"]
    writer = get_stream_writer()
    writer(
        {
            "task_number": task_number,
            "stage": "decide",
            "status": "running",
            "message": f"任务 {task_number} 正在判断下一步行动……",
        }
    )
    llm = create_llm("research").bind_tools(RESEARCH_TOOLS)

    response = invoke_llm(
        llm,
        [
            SystemMessage(content=RESEARCH_AGENT_SYSTEM_PROMPT),
            *state["messages"],
        ]
    )

    return {
        "messages": [response],
    }


def execute_task_tools_node(state: TaskState) -> dict:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError("工具节点必须接收模型消息")

    calls = last_message.tool_calls

    # 复制来源对象，避免原地修改旧状态
    sources = [source.model_copy() for source in state["current_results"]]

    tool_messages = []
    writer = get_stream_writer()
    task_number = state["task_number"]

    for index, call in enumerate(calls):
        name = call["name"]
        args = call["args"]
        call_id = call["id"]

        if index >= MAX_TOOLS_PER_ROUND:
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(
                        {"error": ("本轮工具执行数量已达上限，本次调用未执行。")},
                        ensure_ascii=False,
                    ),
                    tool_call_id=call_id,
                    name=name,
                )
            )
            continue

        writer(
            {
                "task_number": task_number,
                "stage": "tools",
                "status": "running",
                "message": f"任务 {task_number} 正在执行工具：{name}",
            }
        )

        try:
            if name == "search_web":
                if set(args) != {"query"}:
                    raise ValueError("搜索工具只接收 query 参数")

                query = args["query"]
                if not isinstance(query, str) or not query.strip():
                    raise ValueError("query 必须是非空字符串")

                found = search_web(query.strip())

                # 已有来源不重新编号，新来源去重后追加
                url_to_id = {
                    source.url: number for number, source in enumerate(sources, start=1)
                }

                returned_ids = []

                for source in found:
                    source_id = url_to_id.get(source.url)

                    if source_id is None:
                        sources.append(source)
                        source_id = len(sources)
                        url_to_id[source.url] = source_id

                    if source_id not in returned_ids:
                        returned_ids.append(source_id)

                result = {
                    "sources": [
                        {
                            "source_id": source_id,
                            "title": sources[source_id - 1].title,
                            "url": sources[source_id - 1].url,
                            "snippet": sources[source_id - 1].snippet[:1500],
                        }
                        for source_id in returned_ids
                    ]
                }

            elif name == "read_webpage":
                if set(args) != {"source_id"}:
                    raise ValueError("网页读取工具只接收 source_id 参数")

                source_id = args["source_id"]

                # 用 type 排除 True/False，它们在 Python 中也属于 int
                if type(source_id) is not int:
                    raise ValueError("source_id 必须是整数")

                if not 1 <= source_id <= len(sources):
                    raise ValueError("来源编号不存在，请先搜索")

                source = sources[source_id - 1]

                # 已经成功抓取的网页直接复用
                if source.fetch_status != "success":
                    try:
                        source.page_content = fetch_web(source.url)
                        source.fetch_status = "success"
                    except RuntimeError:
                        source.page_content = ""
                        source.fetch_status = "failed"

                if source.fetch_status == "success":
                    usable, issue = assess_page_content(source.page_content)
                    source.content_status = "usable" if usable else "rejected"
                    source.content_issue = issue

                usable_body = (
                    source.fetch_status == "success"
                    and source.content_status == "usable"
                )

                result = {
                    "source_id": source_id,
                    "title": source.title,
                    "fetch_status": source.fetch_status,
                    "material_type": ("网页正文" if usable_body else "搜索摘要"),
                    "content": (source.page_content if usable_body else source.snippet)[
                        :6000
                    ],
                }

            else:
                raise ValueError("未知工具，请使用已提供的工具")

        except ValueError as exc:
            # 参数问题反馈给模型，让它有机会修正
            result = {
                "error": str(exc),
            }

        tool_messages.append(
            ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                name=name,
            )
        )

    return {
        "messages": tool_messages,
        "current_results": sources,
        "tool_rounds": state["tool_rounds"] + 1,
    }


def route_after_decide(state: TaskState) -> str:
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage):
        raise ValueError("决策节点没有返回模型消息")

    if last_message.invalid_tool_calls:
        raise ValueError("模型返回了无法解析的工具调用")

    if last_message.tool_calls:
        return "tools"

    return "summarize"


def route_after_tools(state: TaskState) -> str:
    if state["tool_rounds"] >= MAX_TOOL_ROUNDS:
        return "summarize"

    return "decide"


def summarize_task(
    task: ResearchTask,
    results: list[SearchResult],
    llm: BaseChatModel,
) -> str:
    """
    对搜索结果进行总结，生成研究发现。
    """
    if not results:
        raise ValueError("搜索结果为空，无法总结")

    source_blocks = []

    for index, result in enumerate(results, start=1):
        if (
            result.fetch_status == "success"
            and result.page_content.strip()
            and result.content_status == "usable"
        ):
            content = result.page_content
            material_type = "网页提取正文"
        else:
            content = result.snippet
            material_type = "搜索摘要"

        is_truncated = len(content) > 6000
        visible_content = content[:6000]

        source_blocks.append(
            f"[{index}] {result.title}\n"
            f"链接：{result.url}\n"
            f"正文读取状态：{result.fetch_status}\n"
            f"材料类型：{material_type}\n"
            f"是否截断：{'是' if is_truncated else '否'}\n"
            f"内容：\n{visible_content}\n"
            f"正文内容状态：{result.content_status}\n"
            f"正文检查说明：{result.content_issue or '无'}\n"
        )

    sources_text = "\n\n".join(source_blocks)

    user_message = (
        f"子任务：{task.title}\n研究目的：{task.intent}\n\n搜索资料：\n{sources_text}"
    )

    response = invoke_llm(
        llm,
        [
            ("system", SUMMARIZER_SYSTEM_PROMPT),
            ("human", user_message),
        ]
    )

    return response.content


def plan_node(state: ResearchState) -> dict:
    """
    生成研究计划。
    """
    # 从state中获取topic
    topic = state["topic"]

    # 创建llm客户端
    llm = create_llm("plan")

    # 使用规划提示词和topic调用模型
    user_message = f"研究主题：{topic}"
    response = invoke_llm(
        llm,
        [
            ("system", PLANNER_SYSTEM_PROMPT),
            ("human", user_message),
        ]
    )

    # 用 ResearchPlan.model_validate_json 验证回答
    plan = ResearchPlan.model_validate_json(response.content)

    # 返回任务列表的状态更新
    return {"tasks": plan.tasks}


def task_summarize_node(state: TaskState) -> dict:
    results = state["current_results"]
    task_number = state["task_number"]
    writer = get_stream_writer()

    if not results:
        writer(
            {
                "task_number": task_number,
                "stage": "summarize",
                "status": "skipped",
                "message": f"任务 {task_number} 无可用资料，跳过总结",
            }
        )
        return {"current_summary": "暂无可用资料，无法总结。"}

    writer(
        {
            "task_number": task_number,
            "stage": "summarize",
            "status": "running",
            "message": f"任务 {task_number} 正在生成总结……",
        }
    )

    summary = summarize_task(
        state["task"],
        results,
        create_llm("summarize"),
    )
    if state.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
        summary = (
            "研究边界：已达到工具调用轮数上限，"
            "以下总结基于当前已获取资料，未继续补充检索。\n\n" + summary
        )

    writer(
        {
            "task_number": task_number,
            "stage": "summarize",
            "status": "completed",
            "message": f"任务 {task_number} 总结完成",
        }
    )

    return {"current_summary": summary}


def task_select_materials_node(state: TaskState) -> dict:
    record = TaskResearch(
        task=state["task"], sources=state["current_results"], summary=state["current_summary"],
    )
    task_number = state["task_number"]
    writer = get_stream_writer()

    def progress(event):
        writer({**event, "task_number": task_number, "stage": "select_materials", "status": "running"})

    ids = select_source_ids(state["topic"], record, task_number, progress, create_llm("select"))
    selected, _ = select_task_sources(record, ids, task_number)
    return {"selected_source_ids": ids, "selected_research": selected}


def task_summarize_selected_node(state: TaskState) -> dict:
    selected = state["selected_research"].model_copy(deep=True)
    writer = get_stream_writer()
    writer({
        "task_number": state["task_number"], "stage": "summarize_selected", "status": "running",
        "message": f"已保留 {len(selected.sources)} 条来源，正在整理精选材料……",
    })
    selected.summary = (
        summarize_task(selected.task, selected.sources, create_llm("summarize")) if selected.sources
        else "没有筛选出相关来源，当前任务证据不足。"
    )
    return {"selected_research": selected}


def task_record_node(state: TaskState) -> dict:
    record = TaskResearch(
        task=state["task"],
        sources=state["current_results"],
        summary=state["current_summary"],
    )

    update = {"task_results": {state["task_number"]: record}}
    if "selected_research" in state:
        update["task_materials"] = {
            state["task_number"]: TaskMaterials(
                research=state["selected_research"], source_ids=state["selected_source_ids"],
            ),
        }
    return update


def task_persist_node(state: TaskState) -> dict:
    task_number = state["task_number"]
    record = state["task_results"][task_number]

    save_task_record(
        task_number=task_number,
        record=record,
        output_dir=Path(state["output_dir"]),
        materials=state.get("task_materials", {}).get(task_number),
    )

    writer = get_stream_writer()
    writer(
        {
            "task_number": task_number,
            "stage": "persist",
            "message": f"任务 {task_number} 的研究成果已保存",
        }
    )

    return {}


def collect_node(state: ResearchState) -> dict:
    """检查成果是否齐全，并按原计划顺序整理。"""
    tasks = state["tasks"]
    results = state.get("task_results", {})

    expected = set(range(1, len(tasks) + 1))
    actual = set(results)

    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)

        raise ValueError(
            f"任务成果不完整：缺少任务 {missing}，存在额外任务 {unexpected}"
        )

    ordered_records = [results[task_number] for task_number in range(1, len(tasks) + 1)]

    # 额外检查：成果与原计划中的任务一致
    for task, record in zip(tasks, ordered_records):
        if record.task != task:
            raise ValueError("研究成果与原计划中的任务不一致")

    update = {"completed_research": ordered_records}
    if state.get("workflow_version") == 2:
        materials = state.get("task_materials", {})
        if set(materials) != expected:
            raise ValueError("子任务精选材料不完整")
        records, source_map = build_report_materials(
            ordered_records, {number: item.source_ids for number, item in materials.items()},
        )
        for number, record in enumerate(records, start=1):
            selected = materials[number].research
            if record.task != selected.task or record.sources != selected.sources:
                raise ValueError(f"任务 {number} 的精选材料与原始来源不一致")
            record.summary = selected.summary
        update.update(report_research=records, report_source_map=source_map)
    return update


def format_research_materials(
    records: list[TaskResearch],
    max_source_chars: int = 6000,
    max_summary_chars: int | None = None,
) -> str:
    """
    格式化研究记录，返回一个包含所有任务的字符串。

    ## 任务 1：任务标题
    研究目的：……

    初步总结：
    ……原始总结，保留其中的局部引用 [1]……

    来源对照：
    局部引用 [1] → 最终引用 [T1-S1]
    标题：……
    链接：……
    搜索摘要：……
    """
    blocks = []

    for task_index, research in enumerate(records, start=1):
        summary = research.summary
        if max_summary_chars is not None and len(summary) > max_summary_chars:
            summary = (
                summary[:max_summary_chars]
                + "\n[任务总结已截断，未展示部分不作为本次报告依据]"
            )
        blocks.append(
            f"## 任务 {task_index}：{research.task.title}\n"
            f"研究目的：{research.task.intent}\n\n"
            f"初步总结：\n{summary}\n\n"
            f"来源对照："
        )
        for source_index, source in enumerate(research.sources, start=1):
            if (
                source.fetch_status == "success"
                and source.page_content.strip()
                and source.content_status == "usable"
            ):
                content = source.page_content
                material_type = "网页提取正文"
            else:
                content = source.snippet
                material_type = "搜索摘要"

            is_truncated = len(content) > max_source_chars
            visible_content = content[:max_source_chars]

            blocks.append(
                f"局部引用 [{source_index}] → 最终引用 [T{task_index}-S{source_index}]\n"
                f"标题：{source.title}\n"
                f"链接：{source.url}\n"
                f"正文读取状态：{source.fetch_status}\n"
                f"材料类型：{material_type}\n"
                f"是否截断：{'是' if is_truncated else '否'}\n"
                f"内容：\n{visible_content}\n"
                f"正文内容状态：{source.content_status}\n"
                f"正文检查说明：{source.content_issue or '无'}\n"
            )
    return "\n\n".join(blocks)


def select_source_ids(topic, record, task_number, writer, llm) -> list[int]:
    writer({"message": f"正在筛选任务 {task_number} 的报告材料……"})
    candidates = []
    for source_id, source in enumerate(record.sources, start=1):
        usable_body = (
            source.fetch_status == "success"
            and source.content_status == "usable"
            and bool(source.page_content.strip())
        )
        candidates.append(
            {
                "source_id": source_id,
                "title": source.title[:200],
                "url": source.url[:500],
                "material_type": "正文片段" if usable_body else "搜索摘要",
                "preview": (source.page_content if usable_body else source.snippet)[
                    :800
                ],
            }
        )

    def choose(items):
        response = invoke_llm(
            llm,
            [
                SystemMessage(content=SOURCE_SELECTOR_SYSTEM_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "research_topic": topic[:2000],
                            "task_title": record.task.title[:1000],
                            "task_intent": record.task.intent[:1000],
                            "candidates": items,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        ids = SourceSelection.model_validate_json(response.content).source_ids
        if len(ids) != len(set(ids)):
            raise ValueError(f"任务 {task_number} 的筛选来源编号重复")
        available = {item["source_id"] for item in items}
        if not set(ids) <= available:
            raise ValueError(f"任务 {task_number} 选择了候选范围外的来源")
        return ids

    # 先按10条短片段分批初选，候选过多时再统一决选。
    finalists = []
    for start in range(0, len(candidates), 10):
        finalists.extend(choose(candidates[start : start + 10]))
    if len(finalists) > 5:
        by_id = {item["source_id"]: item for item in candidates}
        finalists = choose([by_id[source_id] for source_id in finalists])
    return finalists


def select_materials_node(state: ResearchState) -> dict:
    """分批选择来源，再按新编号重新总结；保留完整研究成果。"""
    records = state["completed_research"]
    writer = get_stream_writer()
    llm = create_llm("select")
    selected_by_task = {}

    for task_number, record in enumerate(records, start=1):
        selected_by_task[task_number] = select_source_ids(
            state["topic"], record, task_number, writer, llm,
        )

    report_records, source_map = build_report_materials(records, selected_by_task)
    for task_number, record in enumerate(report_records, start=1):
        if not record.sources:
            record.summary = "没有筛选出相关来源，当前任务证据不足。"
            continue
        writer(
            {
                "message": f"任务 {task_number} 保留 {len(record.sources)} 条来源，正在重新总结……"
            }
        )
        record.summary = summarize_task(record.task, record.sources, create_llm("summarize"))

    return {"report_research": report_records, "report_source_map": source_map}


def report_node(state: ResearchState) -> dict:
    """生成最终的研究报告。"""
    topic = state["topic"]
    completed_research = state["report_research"]

    if not any(record.sources for record in completed_research):
        return {"final_report": "暂无可用研究记录，无法生成报告。"}

    max_material_chars = 100_000

    # 多轮搜索可能累积大量来源；摘要与正文都需要逐级裁剪。
    for per_source_chars, per_summary_chars in (
        (6000, 6000),
        (3000, 6000),
        (1500, 4000),
        (750, 3000),
        (300, 2000),
        (100, 1000),
        (0, 0),
    ):
        formatted_materials = format_research_materials(
            completed_research,
            max_source_chars=per_source_chars,
            max_summary_chars=per_summary_chars,
        )

        if len(formatted_materials) <= max_material_chars:
            break
    else:
        raise ValueError("来源元数据已超出报告材料预算，需要减少来源数量")

    user_message = f"研究主题：{topic}\n研究材料：\n{formatted_materials}"
    writer = get_stream_writer()
    if per_source_chars < 6000 or any(
        len(record.summary) > per_summary_chars for record in completed_research
    ):
        writer(
            {
                "message": (
                    f"报告材料已按预算裁剪：每来源最多 {per_source_chars} 字符，"
                    f"每任务总结最多 {per_summary_chars} 字符；来源编号保持不变"
                )
            }
        )
    writer({"message": "开始整合研究材料，生成最终报告……"})
    llm = create_llm("report")
    response = invoke_llm(
        llm,
        [
            ("system", REPORTER_SYSTEM_PROMPT),
            ("human", user_message),
        ]
    )

    report = response.content

    used_ids = extract_citation_ids(report)
    invalid_ids = find_invalid_citations(report, completed_research)

    if not used_ids:
        writer({"message": "引用检查：未识别到 [T任务号-S来源号] 格式的引用"})
    elif invalid_ids:
        writer({"message": f"引用检查发现不存在的编号：{', '.join(invalid_ids)}"})
    else:
        writer({"message": "引用编号检查完成：引用编号均有对应来源"})

    return {
        "final_report": report,
        "invalid_citations": invalid_ids,
        "citation_count": len(used_ids),
    }


def persist_node(state: ResearchState) -> dict:
    """将已完成的研究记录保存到本次输出目录。"""
    output_dir = Path(state["output_dir"])
    save_research_records(state, output_dir)
    return {}


def persist_report_materials_node(state: ResearchState) -> dict:
    save_report_materials(state, Path(state["output_dir"]))
    return {}


def extract_node(state: ResearchState) -> dict:
    """从最终报告中抽取待核对结论；抽查失败保留报告和失败记录。"""
    writer = get_stream_writer()
    writer({"message": "开始抽取待核对结论……"})

    try:
        llm = create_llm("extract")
        items = extract_claims(state["final_report"], llm)
    except Exception as exc:
        logger.warning("结论抽取失败，保留完整报告并跳过证据抽查", exc_info=True)
        writer({"message": "完整报告已生成，结论抽取失败，本次证据抽查未完成，继续整理摘要。"})
        return {
            "claims_to_check": [],
            "evaluation_results": [{
                "stage": "extract", "status": "failed",
                "error_type": type(exc).__name__, "error": str(exc),
            }],
        }

    writer({"message": f"抽取到 {len(items)} 条待核对结论"})
    return {"claims_to_check": items, "evaluation_results": []}


def evaluate_node(state: ResearchState) -> dict:
    """核对抽取的结论与来源。"""
    items = state["claims_to_check"]
    writer = get_stream_writer()

    if not items:
        writer({"message": "没有可核对的检查项，跳过证据评估"})
        return {"evaluation_results": state.get("evaluation_results", [])}

    writer({"message": f"开始评估 {len(items)} 条结论……"})

    llm = create_llm("evaluate")
    results = check_claims(
        items,
        state["report_research"],
        llm,
    )

    return {"evaluation_results": results}


def distill_conclusions_node(state: ResearchState) -> dict:
    """独立生成首页摘要；摘要失败不影响已经生成的完整报告。"""
    writer = get_stream_writer()
    writer({"message": "完整报告已生成，正在凝练核心结论……"})
    try:
        response = invoke_llm(
            create_llm("distill"),
            [
                ("system", CONCLUSION_DISTILLER_SYSTEM_PROMPT),
                ("human", (
                    f"研究主题：{state['topic']}\n\n完整报告：\n{state['final_report']}\n\n"
                    "抽样核验记录（不是对整份报告的完整核验）：\n"
                    + json.dumps(state.get("evaluation_results", []), ensure_ascii=False)
                )),
            ],
        )
        summary = response.content.strip()
        if not summary:
            raise ValueError("摘要为空")
    except Exception:
        logger.warning("结论摘要生成失败，保留完整报告", exc_info=True)
        writer({"message": "完整报告已生成，摘要暂不可用，可直接阅读报告。"})
        return {"report_summary": ""}
    return {"report_summary": summary}
