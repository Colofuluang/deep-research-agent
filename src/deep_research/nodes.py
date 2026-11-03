from langchain_core.language_models.chat_models import BaseChatModel
from .llm import create_llm
from .models import ResearchTask, ResearchPlan, SearchResult, TaskResearch
from .prompts import PLANNER_SYSTEM_PROMPT, SUMMARIZER_SYSTEM_PROMPT, REPORTER_SYSTEM_PROMPT
from .state import ResearchState
from .tools.search import search_web
from .tools.fetch import fetch_web, assess_page_content
from pathlib import Path
from .storage import save_research_records
from langgraph.config import get_stream_writer
from .citations import find_invalid_citations, extract_citation_ids
from .evaluation import extract_claims, check_claims
from time import sleep

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
        if result.fetch_status == "success" and result.page_content.strip() and result.content_status == "usable":
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
        f"子任务：{task.title}\n"
        f"研究目的：{task.intent}\n\n"
        f"搜索资料：\n{sources_text}"
    )

    response = llm.invoke([
        ("system", SUMMARIZER_SYSTEM_PROMPT),
        ("human", user_message),
    ])

    return response.content

def plan_node(state: ResearchState) -> dict:
    """
    生成研究计划。
    """
    # 从state中获取topic
    topic = state["topic"]

    # 创建llm客户端
    llm = create_llm()

    # 使用规划提示词和topic调用模型
    user_message = f"研究主题：{topic}"
    response = llm.invoke([
        ("system", PLANNER_SYSTEM_PROMPT),
        ("human", user_message),
    ])

    # 用 ResearchPlan.model_validate_json 验证回答
    plan = ResearchPlan.model_validate_json(response.content)
    
    # 返回任务列表的状态更新
    return {"tasks": plan.tasks}

def search_node(state: ResearchState) -> dict:
    """搜索当前研究任务的资料。"""
    task_index = state["task_index"]
    task = state["tasks"][task_index]
    writer = get_stream_writer()
    writer({"message": f"任务编号：{task_index + 1}\n任务总数：{len(state['tasks'])}\n任务标题：{task.title}"})
    try: 
        results = search_web(task.query)

    except TimeoutError:
        writer({
            "message": "搜索超时，1 秒后自动重试一次……"
        })
        sleep(1)
        results = search_web(task.query)
        
    return {"current_results": results}
    
def summarize_node(state: ResearchState) -> dict:
    """总结当前研究任务的资料。"""
    results = state["current_results"]

    if not results:
        return {"current_summary": "暂无可用资料，无法总结。"}

    task_index = state["task_index"]
    task = state["tasks"][task_index]
    llm = create_llm()
    summary = summarize_task(task, results, llm)

    return {"current_summary": summary}

def record_node(state: ResearchState) -> dict:
    """保存当前任务的资料与总结。"""
    task_index = state["task_index"]
    task = state["tasks"][task_index]

    record = TaskResearch(
        task=task,
        sources=state["current_results"],
        summary=state["current_summary"],
    )

    return {
        "completed_research": state["completed_research"] + [record]
    }

def advance_node(state: ResearchState) -> dict:
    """切换到下一个研究任务。"""
    task_index = state["task_index"]
    return {"task_index": task_index + 1}


def route_after_advance(state: ResearchState) -> str:
    """判断是否还有未处理的任务。"""
    task_index = state["task_index"]

    if task_index < len(state["tasks"]):
        return "search"
    return "done"

def format_research_materials(
    records: list[TaskResearch],
    max_source_chars: int = 6000,
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
        blocks.append(
            f"## 任务 {task_index}：{research.task.title}\n"
            f"研究目的：{research.task.intent}\n\n"
            f"初步总结：\n{research.summary}\n\n"
            f"来源对照："
        )
        for source_index, source in enumerate(research.sources, start=1):
            if source.fetch_status == "success" and source.page_content.strip() and source.content_status == "usable":
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


def report_node(state: ResearchState) -> dict:
    """生成最终的研究报告。"""
    topic = state["topic"]
    completed_research = state["completed_research"]

    if not completed_research:
        return {"final_report": "暂无可用研究记录，无法生成报告。"}

    max_material_chars = 100_000

    for per_source_chars in (6000, 3000, 1500):
        formatted_materials = format_research_materials(
            completed_research,
            max_source_chars=per_source_chars,
        )

        if len(formatted_materials) <= max_material_chars:
            break
    else:
        raise ValueError("报告材料仍超出预算，需要进一步筛选或压缩")

    user_message = (
        f"研究主题：{topic}\n"
        f"研究材料：\n{formatted_materials}"
    )
    writer = get_stream_writer()
    writer({"message": "开始整合研究材料，生成最终报告……"})
    llm = create_llm()
    response = llm.invoke([
        ("system", REPORTER_SYSTEM_PROMPT),
        ("human", user_message),
    ])

    report = response.content

    used_ids = extract_citation_ids(report)
    invalid_ids = find_invalid_citations(report, completed_research)

    if not used_ids:
        writer({
            "message": "引用检查：未识别到 [T任务号-S来源号] 格式的引用"
        })
    elif invalid_ids:
        writer({
            "message": f"引用检查发现不存在的编号：{', '.join(invalid_ids)}"
        })
    else:
        writer({
            "message": "引用编号检查完成：引用编号均有对应来源"
        })

    return {
        "final_report": report,
        "invalid_citations": invalid_ids,
        "citation_count": len(used_ids),
    }

def fetch_node(state: ResearchState) -> dict:
    updated_results = []

    for source in state["current_results"]:
        updated_source = source.model_copy()

        if updated_source.fetch_status != "success":
            try:
                updated_source.page_content = fetch_web(updated_source.url)
                updated_source.fetch_status = "success"
            except RuntimeError:
                updated_source.page_content = ""
                updated_source.fetch_status = "failed"
        
        if updated_source.fetch_status == "success":
            usable, issue = assess_page_content(updated_source.page_content)

            updated_source.content_status = "usable" if usable else "rejected"
            updated_source.content_issue = issue

        updated_results.append(updated_source)
    return {"current_results": updated_results}

def persist_node(state: ResearchState) -> dict:
    """将已完成的研究记录保存到本次输出目录。"""
    output_dir = Path(state["output_dir"])
    save_research_records(state, output_dir)
    return {}


def extract_node(state: ResearchState) -> dict:
    """从最终报告中抽取待核对结论。"""
    writer = get_stream_writer()
    writer({"message": "开始抽取待核对结论……"})

    llm = create_llm()
    items = extract_claims(state["final_report"], llm)

    writer({"message": f"抽取到 {len(items)} 条待核对结论"})
    return {"claims_to_check": items}


def evaluate_node(state: ResearchState) -> dict:
    """核对抽取的结论与来源。"""
    items = state["claims_to_check"]
    writer = get_stream_writer()

    if not items:
        writer({"message": "没有抽取到检查项，跳过证据评估"})
        return {"evaluation_results": []}

    writer({"message": f"开始评估 {len(items)} 条结论……"})

    llm = create_llm()
    results = check_claims(
        items,
        state["completed_research"],
        llm,
    )

    return {"evaluation_results": results}