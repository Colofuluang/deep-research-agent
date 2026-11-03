import requests
from bs4 import BeautifulSoup
from ..models import SearchResult

def assess_page_content(
    text: str,
    min_chars: int = 200
) -> tuple[bool, str]:
    """评估网页正文是否符合要求。"""
    cleaned = text.strip()

    if not cleaned:
        return False, "正文为空"
    
    if len(cleaned) < min_chars:
        return False, "正文字符数不足"
    
    return True, ""

def fetch_web(url: str) -> str:
    """从互联网获取网页内容。"""
    # 输入来源URL
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("网页请求失败") from exc

    # 获取可供阅读的正文，不是HRML
    content_type = (
        response.headers.get("Content-Type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    if content_type != "text/html":
        raise RuntimeError("网页内容不是HTML格式")
    
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()


    content = soup.find("article") or soup.find("main") or soup.body or soup
    text = content.get_text(separator="\n", strip=True)
    # 成功返回非空文本
    if not text:
        raise RuntimeError("未提取到网页正文")

    return text.strip()

if __name__ == "__main__":
    source = SearchResult(
        title="正文读取测试",
        url="https://juejin.cn/post/7651909848472567849",
    )

    source.page_content = fetch_web(source.url)
    source.fetch_status = "success"

    print("标题：", source.title)
    print("搜索摘要：", source.snippet)
    print("读取状态：", source.fetch_status)
    print("正文字符数：", len(source.page_content))
    print("正文预览：", source.page_content[:500])