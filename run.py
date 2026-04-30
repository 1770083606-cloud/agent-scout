"""AgentScout - AI Agent Token 侦察兵
垂直追踪 AI Agent 赛道新 Token，AI 智能评分筛选

启动方式:
    python run.py
"""
import asyncio
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import TELEGRAM_BOT_TOKEN
from src.bot.bot import create_bot, post_init, post_shutdown


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ 错误: 未设置 TELEGRAM_BOT_TOKEN")
        print("请在 .env 文件中配置你的 Bot Token")
        sys.exit(1)

    print("🤖 AgentScout - AI Agent Token 侦察兵")
    print("=" * 40)

    app = create_bot()

    # 注册启动和关闭回调
    app.post_init = post_init
    app.post_shutdown = post_shutdown

    print("✅ Bot 配置完成，正在启动...")
    print("📡 按 Ctrl+C 停止\n")

    # 启动 Bot
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
