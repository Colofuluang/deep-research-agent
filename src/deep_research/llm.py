"""集中管理请求超时；仅报告申请32K输出，其余使用服务端默认，重试只使用SDK的一层。"""
from typing import Literal

import httpx
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from .config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL


ModelStage = Literal[
    "plan", "research", "select", "summarize", "report", "extract", "evaluate", "distill",
]

# 读取超时秒数，不是整项研究的总时限。
READ_TIMEOUTS: dict[ModelStage, float] = {
    "plan": 60,
    "research": 60,
    "select": 60,
    "summarize": 120,
    "report": 180,
    "extract": 60,
    "evaluate": 60,
    "distill": 60,
}


def create_llm(stage: ModelStage) -> ChatDeepSeek:
    read_timeout = READ_TIMEOUTS[stage]
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        timeout=httpx.Timeout(read_timeout, connect=10, write=30, pool=10),
        max_tokens=32768 if stage == "report" else None,
        # 避免服务端默认思考模式增加等待时间。
        extra_body={"thinking": {"type": "disabled"}},
        max_retries=1,
    )


def invoke_llm(model, messages) -> AIMessage:
    """识别服务端截断，避免半截JSON、工具参数或报告进入后续流程。"""
    response = model.invoke(messages)
    if response.response_metadata.get("finish_reason") == "length":
        raise RuntimeError("模型服务端返回的响应已截断（finish_reason=length）；请检查输出预算或上下文长度后恢复研究")
    return response
