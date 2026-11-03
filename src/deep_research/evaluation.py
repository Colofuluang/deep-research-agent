from langchain_core.language_models.chat_models import BaseChatModel

from .models import CitationAssessment
from .prompts import CLAIM_CHECKER_SYSTEM_PROMPT
from .citations import resolve_source
from .models import TaskResearch
from .models import ClaimToCheck, ClaimExtraction
from .prompts import CLAIM_EXTRACTOR_SYSTEM_PROMPT
from .citations import extract_citation_ids


def check_claim(
    claim: str, 
    evidence: str,
    llm: BaseChatModel,
) -> CitationAssessment:
    if not claim.strip():
        raise ValueError("待核对结论不能为空")

    if not evidence.strip():
        raise ValueError("来源片段不能为空")
        
    message = [
        ("system", CLAIM_CHECKER_SYSTEM_PROMPT),
        (
            "human", 
            f"待核对结论：\n{claim}\n\n"
            f"来源片段：\n{evidence}"
        ),
   ]

    response = llm.invoke(message)
    check = CitationAssessment.model_validate_json(response.content)
    if check.verdict in {"supported", "partially_supported"}:
        if not check.evidence_quote.strip():
            raise ValueError("支持或部分支持的判断必须提供来源原文")

    if check.evidence_quote:
        if check.evidence_quote not in evidence:
            print(
                "[DEBUG-citation] 当前结论：",
                claim,
                flush=True,
            )
            print(
                "[DEBUG-citation] 模型返回的引文：",
                repr(check.evidence_quote),
                flush=True,
            )
            raise ValueError("评估返回的引文不在来源片段中")
    return check


def check_claims(
    items: list[ClaimToCheck],
    records: list[TaskResearch],
    llm: BaseChatModel,
) -> list[dict]:
    """综合各条结论引用的来源，逐条评估。"""
    results = []

    for item in items:
        try:
            blocks = []
            source_texts = []
            materials = []

            for citation_id in item.citation_ids:
                source = resolve_source(citation_id, records)

                if (
                    source.fetch_status == "success"
                    and source.content_status == "usable"
                    and source.page_content.strip()
                ):
                    text = source.page_content[:6000]
                    material_type = "网页正文"
                else:
                    text = source.snippet[:6000]
                    material_type = "搜索摘要"

                if not text.strip():
                    raise ValueError(
                        f"来源没有可用文本：{citation_id}"
                    )

                source_texts.append(text)

                materials.append({
                    "citation_id": citation_id,
                    "material_type": material_type,
                })

                blocks.append(
                    f"来源 [{citation_id}]\n"
                    f"材料类型：{material_type}\n"
                    f"内容：\n{text}"
                )

            # 来源循环结束后，再进行综合评估
            evidence = "\n\n".join(blocks)
            assessment = check_claim(item.claim, evidence, llm)

            # 引文必须属于某一份来源，不能跨来源拼接
            quote = assessment.evidence_quote
            if quote and not any(
                quote in text for text in source_texts
            ):
                raise ValueError(
                    "引文必须来自某一份来源的连续原文"
                )

            results.append({
                "claim": item.claim,
                "citation_ids": item.citation_ids,
                "status": "success",
                "materials": materials,
                "assessment": assessment.model_dump(mode="json"),
            })

        except Exception as exc:
            results.append({
                "claim": item.claim,
                "citation_ids": item.citation_ids,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    return results

def extract_claims(
    report: str,
    llm: BaseChatModel,
) -> list[ClaimToCheck]:
    """从报告中抽取最多三个待核对项。"""
    if not report.strip():
        raise ValueError("研究报告不能为空")

    if not extract_citation_ids(report):
        return []

    messages = [
        ("system", CLAIM_EXTRACTOR_SYSTEM_PROMPT),
        ("human", f"研究报告：\n{report}"),
    ]

    response = llm.invoke(messages)

    extraction = ClaimExtraction.model_validate_json(response.content)

    for item in extraction.items:
        if item.claim not in report:
            raise ValueError("抽取的结论不是报告中的连续原文")

        actual_ids = extract_citation_ids(item.claim)
        if set(item.citation_ids) != actual_ids:
            raise ValueError("引用编号与结论原文中的标记不一致")

    return extraction.items