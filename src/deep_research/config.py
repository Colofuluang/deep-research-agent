# 读取配置：模型、API 密钥、研究预算
import os 
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

if not DEEPSEEK_API_KEY:
    raise ValueError("请在项目根目录的 .env 中配置 DEEPSEEK_API_KEY")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    raise ValueError("请在项目根目录的 .env 中配置 TAVILY_API_KEY")