"""配置管理"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# DexScreener
DEXSCREENER_API_URL = os.getenv("DEXSCREENER_API_URL", "https://api.dexscreener.com")

# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Scan settings
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "120"))
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "0"))
CHAINS = [c.strip() for c in os.getenv("CHAINS", "solana,base").split(",")]

# AI Agent 相关关键词
AI_KEYWORDS = [
    "ai", "agent", "gpt", "llm", "artificial",
    "intelligence", "neural", "machine learning",
    "deep learning", "autonomous", "virtual",
    "claude", "gemini", "lama", "mistral",
    "trading bot", "ai agent", "defi ai",
]

# 数据库
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agent_scout.db")
