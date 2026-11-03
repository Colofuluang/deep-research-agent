# 创建模型客户端
from langchain_deepseek import ChatDeepSeek
from .config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

def create_llm():
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        timeout=60,
        max_retries=1,
    )

if __name__ == "__main__":
    llm = create_llm()
    response = llm.invoke("你好")
    print(response.content)
