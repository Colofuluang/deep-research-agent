# 研究任务、来源、发现的数据结构
from pydantic import BaseModel, Field
from typing import Literal


class ResearchTask(BaseModel):
    title: str = Field(min_length=1, description="子任务标题")
    intent: str = Field(min_length=1, description="研究这个子任务的目的")
    query: str = Field(min_length=1, description="用于搜索的查询词")

class ResearchPlan(BaseModel):
    tasks: list[ResearchTask] = Field(min_length=3, max_length=5, description="包含三个到五个研究任务")

class SearchResult(BaseModel):
    title: str = Field(min_length=1, description="网页标题")
    url: str = Field(min_length=1, description="网页地址")
    snippet: str = Field(default="", description="搜索结果摘要")  
    page_content: str = Field(default="", description="网页正文内容")
    fetch_status: Literal["not_fetched", "success", "failed"] = "not_fetched"
    content_status: Literal["not_checked", "usable", "rejected"] = "not_checked"
    content_issue: str = ""

class TaskResearch(BaseModel):
    task: ResearchTask
    sources: list[SearchResult]
    summary: str
    

class CitationAssessment(BaseModel):
    verdict: Literal[
        "supported",
        "partially_supported",
        "unsupported",
    ] = Field(description="来源对结论的支持程度")

    reason: str = Field(
        min_length=1,
        description="判断理由，说明结论与来源是否一致",
    )

    evidence_quote: str = Field(
        default="",
        description="支持判断的来源原文；没有对应片段时为空",
    )

class ClaimToCheck(BaseModel):
    claim: str = Field(
        min_length=1,
        description="从报告原样复制的连续原文，包含引用标记",
    )
    citation_ids: list[str] = Field(
        min_length=1,
        description="该段原文中的引用编号，例如 T1-S5",
    )


class ClaimExtraction(BaseModel):
    items: list[ClaimToCheck] = Field(
        default_factory=list,
        max_length=3,
        description="最多三个待核对项；没有合适结论时为空",
    )