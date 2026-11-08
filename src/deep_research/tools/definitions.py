RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "搜索网页，获得标题、来源编号和摘要。缺少资料或需要补充证据时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "明确的搜索查询",
                        "minLength": 1,
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": (
                "读取搜索结果中的网页正文。"
                "摘要不足以判断或需要核实细节时使用。"
                "只能使用搜索工具已经返回的来源编号。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "integer",
                        "description": "当前研究任务内的来源编号，从1开始",
                        "minimum": 1,
                    }
                },
                "required": ["source_id"],
                "additionalProperties": False,
            },
        },
    },
]

MAX_TOOL_ROUNDS = 4
MAX_TOOLS_PER_ROUND = 2
