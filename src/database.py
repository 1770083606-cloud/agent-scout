"""轻量数据库：SQLite 封装"""
import sqlite3
import os
from datetime import datetime
from src.config import DB_PATH


def get_db():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    c = conn.cursor()

    # 已扫描的 Token 记录（去重）
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            address TEXT PRIMARY KEY,
            name TEXT,
            symbol TEXT,
            chain TEXT,
            dex_screener_id TEXT,
            first_seen TEXT,
            market_cap REAL,
            liquidity REAL,
            volume_24h REAL,
            description TEXT,
            ai_score INTEGER DEFAULT 0,
            score_github INTEGER DEFAULT 0,
            score_social INTEGER DEFAULT 0,
            score_safety INTEGER DEFAULT 0,
            score_liquidity INTEGER DEFAULT 0,
            score_team INTEGER DEFAULT 0,
            is_ai_related INTEGER DEFAULT 1,
            analyzed INTEGER DEFAULT 0,
            pushed INTEGER DEFAULT 0
        )
    """)

    # 每日简报记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT UNIQUE,
            token_count INTEGER,
            report_text TEXT,
            sent_at TEXT
        )
    """)

    # 用户订阅记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plan TEXT DEFAULT 'free',
            subscribed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_token(token_data: dict):
    """保存或更新 Token 数据"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR REPLACE INTO tokens 
            (address, name, symbol, chain, dex_screener_id, first_seen,
             market_cap, liquidity, volume_24h, description, 
             ai_score, score_github, score_social, score_safety, 
             score_liquidity, score_team, is_ai_related, analyzed, pushed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_data.get("address"),
            token_data.get("name"),
            token_data.get("symbol"),
            token_data.get("chain"),
            token_data.get("dex_screener_id"),
            token_data.get("first_seen", datetime.utcnow().isoformat()),
            token_data.get("market_cap"),
            token_data.get("liquidity"),
            token_data.get("volume_24h"),
            token_data.get("description"),
            token_data.get("ai_score", 0),
            token_data.get("score_github", 0),
            token_data.get("score_social", 0),
            token_data.get("score_safety", 0),
            token_data.get("score_liquidity", 0),
            token_data.get("score_team", 0),
            token_data.get("is_ai_related", 1),
            token_data.get("analyzed", 0),
            token_data.get("pushed", 0),
        ))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] save_token: {e}")
    finally:
        conn.close()


def get_unpushed_tokens(limit=10):
    """获取已分析但未推送的 Token"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM tokens 
        WHERE analyzed = 1 AND pushed = 0 AND is_ai_related = 1
        ORDER BY ai_score DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_as_pushed(address: str):
    """标记 Token 已推送"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE tokens SET pushed = 1 WHERE address = ?", (address,))
    conn.commit()
    conn.close()


def get_today_tokens():
    """获取今天的 Token"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM tokens 
        WHERE first_seen LIKE ? AND is_ai_related = 1 AND analyzed = 1
        ORDER BY ai_score DESC
    """, (f"{today}%",))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_subscriber(user_id: int, username: str = "", plan: str = "free"):
    """添加用户订阅"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO subscribers (user_id, username, plan, subscribed_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, plan, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_subscriber_count():
    """获取订阅者数量"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM subscribers")
    count = c.fetchone()["count"]
    conn.close()
    return count
