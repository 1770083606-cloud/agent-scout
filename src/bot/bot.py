"""Telegram Bot - 用户交互层"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from datetime import datetime

from src.config import TELEGRAM_BOT_TOKEN, SCAN_INTERVAL
from src.database import (
    init_db, get_today_tokens, get_unpushed_tokens,
    mark_as_pushed, add_subscriber, get_subscriber_count
)
from src.scanners.dexscreener import DexScreenerScanner
from src.scorers.ai_scorer import AIScorer


# 全局扫描器和评分器
scanner = None
scorer = None


def format_token_message(token: dict) -> str:
    """格式化单个 Token 的推送消息"""
    score = token.get("ai_score", 0)
    symbol = token.get("symbol", "?")
    name = token.get("name", "Unknown")
    chain = token.get("chain", "?")
    mc = token.get("market_cap", 0)
    liq = token.get("liquidity", 0)
    vol = token.get("volume_24h", 0)
    url = token.get("token_url", "")

    # 星级
    if score >= 80:
        stars = "⭐⭐⭐⭐⭐"
    elif score >= 60:
        stars = "⭐⭐⭐⭐"
    elif score >= 40:
        stars = "⭐⭐⭐"
    elif score >= 20:
        stars = "⭐⭐"
    else:
        stars = "⭐"

    # 维度表情
    def dim_emoji(score, threshold_low=6, threshold_mid=12):
        if score >= threshold_mid:
            return "✅"
        elif score >= threshold_low:
            return "⚠️"
        else:
            return "❌"

    sg = token.get("score_github", 0)
    ss = token.get("score_social", 0)
    sf = token.get("score_safety", 0)
    sl = token.get("score_liquidity", 0)
    st = token.get("score_team", 0)

    risk = token.get("risk_note", "")

    msg = f"""🤖 <b>AgentScout · AI Agent 新币侦察</b>

<b>Token:</b> <a href="{url}">${symbol}</a> — {name}
<b>链:</b> {chain.upper()}
<b>市值:</b> ${mc:,.0f} | <b>流动性:</b> ${liq:,.0f}
<b>24h 交易量:</b> ${vol:,.0f}

<b>AI 评分: {score}/100</b> {stars}

📊 <b>维度详情:</b>
  GitHub: {sg}/20 {dim_emoji(sg)}
  社交媒体: {ss}/20 {dim_emoji(ss)}
  合约安全: {sf}/20 {dim_emoji(sf)}
  流动性: {sl}/20 {dim_emoji(sl)}
  团队: {st}/20 {dim_emoji(st)}
"""

    if risk:
        msg += f"\n⚠️ <b>风险提示:</b> {risk}"

    msg += "\n\n💡 本工具仅提供信息参考，不构成投资建议。加密货币投资风险极高，请自行研究后决策。"

    return msg


def format_daily_report(tokens: list[dict]) -> str:
    """格式化每日简报"""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if not tokens:
        return f"""📋 <b>AgentScout 每日简报 — {today}</b>

今天没有发现新的 AI Agent Token。
市场平静中... 🔍"""

    header = f"""📋 <b>AgentScout 每日简报 — {today}</b>
发现 <b>{len(tokens)}</b> 个新 AI Agent Token
按 AI 评分排序 👇\n"""

    body = ""
    for i, t in enumerate(tokens[:10], 1):
        score = t.get("ai_score", 0)
        symbol = t.get("symbol", "?")
        mc = t.get("market_cap", 0)
        liq = t.get("liquidity", 0)
        url = t.get("token_url", "")

        if score >= 60:
            tag = "🔥"
        elif score >= 40:
            tag = "👍"
        else:
            tag = "👁️"

        body += f"\n{i}. {tag} <a href=\"{url}\">${symbol}</a> — 评分 {score}/100 | MC ${mc:,.0f} | Liq ${liq:,.0f}\n"

    footer = "\n💡 查看某个 Token 的详细分析，发送 /detail [符号]\n\n💡 <b>AgentScout</b> — 只帮你找到值得关注的 AI Agent Token"

    return header + body + footer


# ---- Bot 命令处理 ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 命令"""
    user = update.effective_user

    add_subscriber(user.id, user.username or "")

    welcome = f"""👋 你好，<b>{user.first_name}</b>！

欢迎使用 <b>AgentScout</b> 🤖
AI Agent 赛道垂直新币追踪 + 智能评分

📋 <b>功能列表:</b>
/daily — 查看今日 AI Agent 新币简报
/scan — 立即扫描最新 Token
/detail &lt;符号&gt; — 查看某个 Token 的详细评分
/score &lt;符号&gt; — 对某个 Token 重新评分
/help — 查看帮助

⚡ 本 Bot 自动每 {SCAN_INTERVAL // 60} 分钟扫描一次链上新 Token
💎 发现高评分 AI Agent Token 会即时推送给你"""

    keyboard = [
        [InlineKeyboardButton("📋 今日简报", callback_data="daily"),
         InlineKeyboardButton("🔍 立即扫描", callback_data="scan")],
        [InlineKeyboardButton("❓ 帮助", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome, parse_mode="HTML", reply_markup=reply_markup)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help 命令"""
    help_text = """📖 <b>AgentScout 使用说明</b>

<b>命令列表:</b>
• <code>/start</code> — 开始使用 Bot
• <code>/daily</code> — 查看今日新币简报
• <code>/scan</code> — 立即扫描链上新 Token
• <code>/detail &lt;符号&gt;</code> — 查看详细评分（如 /detail AIA）
• <code>/help</code> — 显示本帮助

<b>工作原理:</b>
1. Bot 每 2 分钟自动扫描 Solana/Base 链上的新 Token
2. 通过关键词筛选出 AI Agent 相关项目
3. 用 AI 从 5 个维度评分（GitHub/社交/安全/流动性/团队）
4. 高评分 Token 会自动推送给你

<b>评分说明:</b>
• 🌟 80+ = 优质项目（稀缺）
• ⭐ 60-79 = 值得关注
• 👍 40-59 = 一般，谨慎
• 👁️ 0-39 = 质量较低

⚠️ <b>免责声明:</b>
本工具仅提供链上数据分析和信息参考，不构成任何投资建议。"""

    await update.message.reply_text(help_text, parse_mode="HTML")


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/daily - 查看今日简报"""
    await update.message.reply_text("🔍 正在生成今日简报...", parse_mode="HTML")

    tokens = get_today_tokens()
    report = format_daily_report(tokens)

    await update.message.reply_text(report, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scan - 立即扫描"""
    await update.message.reply_text("🔍 正在扫描链上新 Token...\n这可能需要 30-60 秒，请稍候...", parse_mode="HTML")

    try:
        new_tokens = await scanner.scan()
        if not new_tokens:
            await update.message.reply_text("😔 暂时没有发现新的 AI Agent Token。")
            return

        # 评分并推送 top 5
        await update.message.reply_text(f"🎯 发现 {len(new_tokens)} 个 AI Agent 相关 Token，正在评分...", parse_mode="HTML")

        scored = []
        for t in new_tokens[:10]:  # 最多评 10 个，省 API 调用
            scores = await scorer.score_token(t)
            t.update(scores)
            t["analyzed"] = 1
            from src.database import save_token
            save_token(t)
            scored.append(t)

        scored.sort(key=lambda x: x.get("ai_score", 0), reverse=True)

        # 推送 top 3
        for t in scored[:3]:
            msg = format_token_message(t)
            await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
            mark_as_pushed(t["address"])

        if len(scored) > 3:
            await update.message.reply_text(
                f"📊 还有 {len(scored) - 3} 个 Token 已记录，发送 /daily 查看",
                parse_mode="HTML"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ 扫描出错: {str(e)}", parse_mode="HTML")


async def cmd_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/detail <符号> - 查看详细评分"""
    if not context.args:
        await update.message.reply_text("用法: /detail <符号>\n例如: /detail AIA", parse_mode="HTML")
        return

    symbol = context.args[0].upper().replace("$", "")

    from src.database import get_db
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM tokens WHERE symbol = ? AND analyzed = 1 ORDER BY ai_score DESC LIMIT 1", (symbol,))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(f"🔍 未找到 ${symbol} 的评分记录。\n该 Token 可能尚未被扫描，请稍后重试。", parse_mode="HTML")
        return

    token = dict(row)
    msg = format_token_message(token)
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理内联按钮回调"""
    query = update.callback_query
    await query.answer()

    if query.data == "daily":
        tokens = get_today_tokens()
        report = format_daily_report(tokens)
        await query.edit_message_text(report, parse_mode="HTML", disable_web_page_preview=True)
    elif query.data == "scan":
        await query.edit_message_text("🔍 请使用 /scan 命令开始扫描", parse_mode="HTML")
    elif query.data == "help":
        await cmd_help(update, context)


# ---- 定时任务 ----

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """定时扫描任务"""
    from src.database import save_token

    try:
        new_tokens = await scanner.scan()

        for t in new_tokens:
            # 检查是否已存在
            from src.database import get_db
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT address FROM tokens WHERE address = ?", (t["address"],))
            exists = c.fetchone()
            conn.close()

            if exists:
                continue

            # 评分
            scores = await scorer.score_token(t)
            t.update(scores)
            t["analyzed"] = 1
            save_token(t)

            # 高分 Token 推送
            if t["ai_score"] >= 50:
                msg = format_token_message(t)
                # 推送给所有订阅用户
                subs = get_all_subscribers()
                for user_id in subs:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                    except Exception:
                        pass  # 用户可能屏蔽了 Bot
                mark_as_pushed(t["address"])

            print(f"[Scheduled] Scored ${t['symbol']}: {t['ai_score']}/100")

    except Exception as e:
        print(f"[Scheduled] Scan error: {e}")


async def scheduled_daily_report(context: ContextTypes.DEFAULT_TYPE):
    """定时推送每日简报"""
    tokens = get_today_tokens()

    if not tokens:
        return

    report = format_daily_report(tokens)
    subs = get_all_subscribers()

    for user_id in subs:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=report,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass


def get_all_subscribers() -> list[int]:
    """获取所有订阅用户 ID"""
    from src.database import get_db
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM subscribers")
    rows = c.fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


# ---- Bot 创建 ----

def create_bot() -> Application:
    """创建并配置 Telegram Bot"""
    global scanner, scorer

    # 初始化
    init_db()
    scanner = DexScreenerScanner()
    scorer = AIScorer()

    # 创建 Bot
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 注册命令
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("detail", cmd_detail))

    # 注册按钮回调
    app.add_handler(CallbackQueryHandler(button_callback))

    # 注册定时任务
    job_queue = app.job_queue

    # 扫描任务
    job_queue.run_repeating(
        scheduled_scan,
        interval=SCAN_INTERVAL,
        first=10,  # 启动 10 秒后首次运行
        name="scan_new_tokens"
    )

    # 每日简报 (UTC 0:00 = 北京时间 8:00)
    job_queue.run_daily(
        scheduled_daily_report,
        time=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).time(),
        name="daily_report"
    )

    return app


async def post_init(app: Application):
    """Bot 启动后的初始化"""
    global scanner, scorer
    scanner = DexScreenerScanner()
    scorer = AIScorer()
    print("[Bot] AgentScout started!")


async def post_shutdown(app: Application):
    """Bot 关闭时清理"""
    global scanner, scorer
    if scanner:
        await scanner.close()
    if scorer:
        await scorer.close()
    print("[Bot] AgentScout stopped.")
