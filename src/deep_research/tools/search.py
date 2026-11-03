from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError
from ..config import TAVILY_API_KEY
from ..models import SearchResult


def search_web(query: str) -> list[SearchResult]:
    """调用 Tavily 搜索，并统一结果结构、去除重复 URL。"""
    query = query.strip()

    if not query:
        raise ValueError("查询词不能为空")

    if not TAVILY_API_KEY:
        raise ValueError(
            "请在项目根目录的 .env 中配置 TAVILY_API_KEY"
        )

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)

        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=False,
            include_raw_content=False,
            timeout=60,
        )
    except TavilyTimeoutError:
        raise TimeoutError("Tavily 搜索超时") from None
        
    except Exception as exc:
        # 在 SDK 调用边界保留错误类型，不输出可能包含密钥的原始错误。
        raise RuntimeError(
            f"Tavily 搜索失败（{type(exc).__name__}），"
            "请检查密钥、额度与网络"
        ) from None

    results = []
    seen_urls = set()

    for item in response.get("results", []):
        url = item.get("url") or ""
        title = item.get("title") or ""

        if not url or not title or url in seen_urls:
            continue

        seen_urls.add(url)

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=item.get("content") or "",
            )
        )

    return results


if __name__ == "__main__":
    results = search_web("AI Agent 的架构与核心组件")

    if not results:
        print("没有相关结果")

    for index, result in enumerate(results, start=1):
        print(f"\n[{index}] {result.title}")
        print(f"链接：{result.url}")
        print(f"摘要：{result.snippet}")