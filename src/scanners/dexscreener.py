"""DexScreener API 扫描器 - 拉取新 Token 数据"""
import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional
from src.config import DEXSCREENER_API_URL, CHAINS, AI_KEYWORDS
from src.database import save_token, get_db


class DexScreenerScanner:
    """DexScreener 新币扫描器"""

    BASE_URL = DEXSCREENER_API_URL
    CHAIN_MAP = {
        "solana": "solana",
        "base": "base",
        "ethereum": "ethereum",
    }

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self._seen_ids = set()

    async def close(self):
        await self.client.aclose()

    def _is_ai_related(self, name: str, symbol: str, description: str = "") -> tuple[bool, int]:
        """
        判断 Token 是否与 AI Agent 相关
        返回: (是否相关, 匹配度分数 0-3)
        """
        text = f"{name} {symbol} {description}".lower()
        matches = 0

        for keyword in AI_KEYWORDS:
            if keyword.lower() in text:
                matches += 1

        # 阈值：至少匹配 1 个关键词
        is_related = matches >= 1
        return is_related, matches

    async def fetch_new_tokens(self, chain: str = "solana") -> list[dict]:
        """
        从 DexScreener 获取最新上线的 Token
        使用 token-boosts 端点获取最新热门新 Token
        """
        tokens = []

        try:
            # 使用 DexScreener 的搜索 API 获取新 Token
            # 搜索 AI 相关关键词
            for keyword in ["AI Agent", "GPT", "AI"]:
                url = f"{self.BASE_URL}/latest/dex/search"
                params = {"q": keyword}

                response = await self.client.get(url, params=params)
                if response.status_code != 200:
                    print(f"[Scanner] API error {response.status_code} for '{keyword}' on {chain}")
                    continue

                data = response.json()
                if not data or "pairs" not in data:
                    continue

                for pair in data.get("pairs", []):
                    chain_id = pair.get("chainId", "")

                    # 过滤链
                    if chain and chain_id != chain:
                        continue

                    token_data = self._parse_pair(pair)
                    if token_data and token_data.get("address") not in self._seen_ids:
                        self._seen_ids.add(token_data["address"])
                        tokens.append(token_data)

        except httpx.TimeoutException:
            print("[Scanner] Request timeout")
        except Exception as e:
            print(f"[Scanner] Error fetching tokens: {e}")

        # 去重
        unique = {}
        for t in tokens:
            unique[t["address"]] = t
        return list(unique.values())

    async def fetch_latest_pairs(self, chain: str = "solana") -> list[dict]:
        """
        使用 DexScreener 的 token profile 搜索
        获取特定链上的最新交易对
        """
        tokens = []
        
        try:
            # 获取指定链上的最新 Boosted Tokens
            url = f"{self.BASE_URL}/token-boosts/latest/v1"
            response = await self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                for token in data:
                    chain_id = token.get("chainId", "")
                    if chain and chain_id != chain:
                        continue
                    
                    token_address = token.get("tokenAddress", "")
                    if not token_address or token_address in self._seen_ids:
                        continue
                    
                    self._seen_ids.add(token_address)
                    
                    # 获取详细信息
                    detail = await self._fetch_pair_detail(chain_id, token_address)
                    if detail:
                        tokens.append(detail)
        except Exception as e:
            print(f"[Scanner] fetch_latest_pairs error: {e}")
        
        return tokens

    async def _fetch_pair_detail(self, chain_id: str, token_address: str) -> Optional[dict]:
        """获取单个 Token 的详细信息"""
        try:
            url = f"{self.BASE_URL}/tokens/v1/{chain_id}/{token_address}"
            response = await self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    pair = data[0]
                    return self._parse_pair(pair)
        except Exception as e:
            print(f"[Scanner] _fetch_pair_detail error: {e}")
        
        return None

    def _parse_pair(self, pair: dict) -> Optional[dict]:
        """解析 DexScreener 的 pair 数据"""
        try:
            base_token = pair.get("baseToken", {})
            quote_token = pair.get("quoteToken", {})
            liquidity = pair.get("liquidity", {})
            volume = pair.get("volume", {})
            
            name = base_token.get("name", "")
            symbol = base_token.get("symbol", "")
            address = base_token.get("address", "")
            chain = pair.get("chainId", "")
            
            if not address or not symbol:
                return None

            # AI 相关性判断
            description = pair.get("info", {}).get("description", "") or ""
            is_ai, match_score = self._is_ai_related(name, symbol, description)

            # 获取价格信息
            price_usd = pair.get("priceUsd", "0")
            price_change = pair.get("priceChange", {})
            
            # 计算市值
            fdv = pair.get("fdv", 0) or 0
            
            # 流动性
            liq_usd = liquidity.get("usd", 0) or 0
            
            # 24h 交易量
            vol_24h = volume.get("h24", 0) or 0

            return {
                "address": address,
                "name": name,
                "symbol": symbol,
                "chain": chain,
                "dex_screener_id": pair.get("pairAddress", ""),
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "market_cap": float(fdv) if fdv else 0,
                "liquidity": float(liq_usd) if liq_usd else 0,
                "volume_24h": float(vol_24h) if vol_24h else 0,
                "price_usd": float(price_usd) if price_usd else 0,
                "price_change_h1": float(price_change.get("h1", 0) or 0),
                "price_change_h6": float(price_change.get("h6", 0) or 0),
                "price_change_h24": float(price_change.get("h24", 0) or 0),
                "description": description,
                "is_ai_related": 1 if is_ai else 0,
                "match_score": match_score,
                "pair_url": f"https://dexscreener.com/{chain}/{pair.get('pairAddress', '')}",
                "token_url": f"https://dexscreener.com/{chain}/{address}",
            }
        except Exception as e:
            print(f"[Scanner] _parse_pair error: {e}")
            return None

    async def scan(self, chains: list[str] = None) -> list[dict]:
        """
        执行完整扫描
        返回所有与 AI Agent 相关的新 Token
        """
        if chains is None:
            chains = CHAINS

        all_tokens = []
        
        for chain in chains:
            print(f"[Scanner] Scanning {chain}...")
            
            # 方法1: 搜索关键词
            search_results = await self.fetch_new_tokens(chain)
            
            # 方法2: 获取最新 Boosted Tokens
            latest_results = await self.fetch_latest_pairs(chain)
            
            # 合并
            chain_tokens = search_results + latest_results
            
            # 只保留 AI 相关的
            ai_tokens = [t for t in chain_tokens if t.get("is_ai_related")]
            all_tokens.extend(ai_tokens)
            
            print(f"[Scanner] Found {len(chain_tokens)} tokens on {chain}, "
                  f"{len(ai_tokens)} AI-related")
            
            # 限速，避免被封
            await asyncio.sleep(2)

        # 去重
        unique = {}
        for t in all_tokens:
            unique[t["address"]] = t
        
        return list(unique.values())


async def run_scan():
    """运行一次扫描（测试用）"""
    scanner = DexScreenerScanner()
    try:
        tokens = await scanner.scan()
        print(f"\n[Scan Result] Found {len(tokens)} AI-related tokens:")
        for t in tokens[:5]:
            print(f"  - ${t['symbol']} ({t['name']}) on {t['chain']} "
                  f"| MC: ${t['market_cap']:,.0f} | "
                  f"Liq: ${t['liquidity']:,.0f}")
        return tokens
    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(run_scan())
