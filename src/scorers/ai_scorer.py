"""AI 评分引擎 - 5 维度评估 AI Agent Token"""
import httpx
import json
from typing import Optional
from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, GITHUB_TOKEN


class AIScorer:
    """
    5 维度 AI 评分引擎：
    1. GitHub 活跃度 (0-20)
    2. 社交媒体真实性 (0-20)
    3. 合约安全性 (0-20)
    4. 流动性健康度 (0-20)
    5. 团队背景 (0-20)
    总分: 0-100
    """

    def __init__(self):
        self.llm_client = httpx.AsyncClient(timeout=60.0)
        self.github_client = httpx.AsyncClient(timeout=30.0)
        self.github_headers = {}
        if GITHUB_TOKEN:
            self.github_headers["Authorization"] = f"token {GITHUB_TOKEN}"

    async def close(self):
        await self.llm_client.aclose()
        await self.github_client.aclose()

    async def score_token(self, token_data: dict) -> dict:
        """
        对单个 Token 进行全面评分
        返回包含各维度分数的字典
        """
        symbol = token_data.get("symbol", "UNKNOWN")
        name = token_data.get("name", "Unknown")
        address = token_data.get("address", "")
        chain = token_data.get("chain", "")
        description = token_data.get("description", "")

        print(f"[Scorer] Scoring ${symbol} on {chain}...")

        # 1. GitHub 活跃度评分
        score_github = await self._score_github(name, symbol, description)

        # 2. 社交媒体评分
        score_social = await self._score_social(name, symbol, description, address, chain)

        # 3. 合约安全性评分
        score_safety = self._score_safety(token_data)

        # 4. 流动性健康度评分
        score_liquidity = self._score_liquidity(token_data)

        # 5. 团队背景评分
        score_team = await self._score_team(name, symbol, description, address)

        # 总分
        total_score = score_github + score_social + score_safety + score_liquidity + score_team

        # 用 LLM 做综合评估和风险提示
        risk_note = await self._generate_risk_note(token_data, {
            "github": score_github,
            "social": score_social,
            "safety": score_safety,
            "liquidity": score_liquidity,
            "team": score_team,
        })

        result = {
            "ai_score": total_score,
            "score_github": score_github,
            "score_social": score_social,
            "score_safety": score_safety,
            "score_liquidity": score_liquidity,
            "score_team": score_team,
            "risk_note": risk_note,
        }

        print(f"[Scorer] ${symbol} total score: {total_score}/100")
        return result

    async def _score_github(self, name: str, symbol: str, description: str) -> int:
        """
        GitHub 活跃度评分 (0-20)
        检查是否有公开的 GitHub 仓库
        """
        score = 5  # 基础分

        try:
            # 搜索 GitHub 仓库
            query = f"{name} {symbol}"
            if len(query) > 3:
                url = f"https://api.github.com/search/repositories"
                params = {"q": query, "per_page": 5, "sort": "stars"}
                headers = self.github_headers.copy()
                headers["Accept"] = "application/vnd.github.v3+json"

                response = await self.github_client.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    repos = data.get("items", [])

                    if repos:
                        best_repo = repos[0]
                        stars = best_repo.get("stargazers_count", 0)
                        forks = best_repo.get("forks_count", 0)
                        updated = best_repo.get("updated_at", "")
                        open_issues = best_repo.get("open_issues_count", 0)

                        # 有仓库 +5
                        score += 3

                        # Star 数评分
                        if stars >= 100:
                            score += 5
                        elif stars >= 30:
                            score += 3
                        elif stars >= 10:
                            score += 2
                        elif stars >= 1:
                            score += 1

                        # Fork 数
                        if forks >= 20:
                            score += 3
                        elif forks >= 5:
                            score += 2
                        elif forks >= 1:
                            score += 1

                        # 最近更新
                        if updated:
                            from datetime import datetime, timezone
                            last_update = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                            days_since = (datetime.now(timezone.utc) - last_update).days
                            if days_since <= 7:
                                score += 4
                            elif days_since <= 30:
                                score += 3
                            elif days_since <= 90:
                                score += 1

        except Exception as e:
            print(f"[Scorer] GitHub check error: {e}")

        return min(score, 20)

    async def _score_social(self, name: str, symbol: str, description: str,
                             address: str, chain: str) -> int:
        """
        社交媒体评分 (0-20)
        基于 LLM 分析 Token 的社交媒体信息
        """
        score = 5  # 基础分

        # 先用规则给分
        if description and len(description) > 50:
            score += 3
        if "twitter.com" in description.lower() or "x.com" in description.lower():
            score += 2
        if "discord" in description.lower():
            score += 2
        if "telegram" in description.lower() or "t.me" in description.lower():
            score += 2

        # 用 LLM 进一步分析
        try:
            prompt = f"""你是一个加密货币项目分析师。请评估以下 AI Agent 项目的社交媒体可信度。

项目名称: {name}
代币符号: ${symbol}
描述: {description}
链上地址: {address[:8]}...{address[-8:]}
链: {chain}

请仅回复一个 0-20 的整数分数，基于以下标准：
- 是否有真实社交媒体存在（Twitter/X, Discord, Telegram）
- 描述是否专业（而非空洞宣传）
- 是否有真实社区互动迹象
- 是否有疑似假粉/机器人的特征

只回复数字，不要其他内容。"""

            llm_score = await self._call_llm(prompt)
            if llm_score is not None:
                # 取规则分和 LLM 分的平均值
                score = int((score + llm_score) / 2)
        except Exception as e:
            print(f"[Scorer] Social LLM error: {e}")

        return min(max(score, 0), 20)

    def _score_safety(self, token_data: dict) -> int:
        """
        合约安全性评分 (0-20)
        基于链上数据的规则判断
        """
        score = 10  # 基础分（假设未知为中等风险）

        liquidity = token_data.get("liquidity", 0)
        market_cap = token_data.get("market_cap", 0)
        description = token_data.get("description", "").lower()

        # 如果有 Liquidity Lock 相关描述，加分
        if "lock" in description or "locked" in description:
            score += 3
        if "renounce" in description or "renounced" in description:
            score += 3

        # 流动性极低 = 危险
        if liquidity > 0 and liquidity < 1000:
            score -= 3
        elif liquidity >= 50000:
            score += 3
        elif liquidity >= 10000:
            score += 2

        # 市值和流动性比例异常
        if market_cap > 0 and liquidity > 0:
            ratio = market_cap / liquidity
            if ratio > 100:
                # FDV/流动性比例过高，可能是骗局
                score -= 3
            elif ratio < 5:
                score += 2

        return min(max(score, 0), 20)

    def _score_liquidity(self, token_data: dict) -> int:
        """
        流动性健康度评分 (0-20)
        """
        score = 5  # 基础分

        liquidity = token_data.get("liquidity", 0)
        volume_24h = token_data.get("volume_24h", 0)
        market_cap = token_data.get("market_cap", 0)

        # 流动性评分
        if liquidity >= 100000:
            score += 7
        elif liquidity >= 50000:
            score += 5
        elif liquidity >= 20000:
            score += 4
        elif liquidity >= 5000:
            score += 2
        elif liquidity > 0:
            score += 1
        else:
            score = 0  # 无流动性 = 0 分

        # 交易量评分
        if volume_24h >= 50000:
            score += 4
        elif volume_24h >= 10000:
            score += 3
        elif volume_24h >= 1000:
            score += 2
        elif volume_24h >= 100:
            score += 1

        # 市值合理性
        if market_cap > 0 and liquidity > 0:
            liq_ratio = liquidity / market_cap
            if liq_ratio >= 0.2:
                score += 4
            elif liq_ratio >= 0.1:
                score += 2
            elif liq_ratio >= 0.05:
                score += 1

        return min(score, 20)

    async def _score_team(self, name: str, symbol: str, description: str,
                           address: str) -> int:
        """
        团队背景评分 (0-20)
        大部分匿名项目，这里分数普遍偏低
        """
        score = 5  # 基础分（匿名团队默认低分）

        try:
            prompt = f"""你是一个加密货币项目分析师。请评估以下 AI Agent 项目的团队可信度。

项目名称: {name}
代币符号: ${symbol}
描述: {description}

请仅回复一个 0-20 的整数分数，基于以下标准：
- 团队是否公开身份（创始人、开发团队）
- 是否有成功的历史项目
- 是否有知名 VC/机构投资背书
- 项目描述是否包含团队信息
- 是否参加过知名黑客松/加速器

注意：大多数加密项目是匿名的，匿名不一定是坏事，但需要更多其他维度的验证。

只回复数字，不要其他内容。"""

            llm_score = await self._call_llm(prompt)
            if llm_score is not None:
                score = llm_score
        except Exception as e:
            print(f"[Scorer] Team LLM error: {e}")

        return min(max(score, 0), 20)

    async def _generate_risk_note(self, token_data: dict, scores: dict) -> str:
        """用 LLM 生成风险提示"""
        symbol = token_data.get("symbol", "Unknown")
        name = token_data.get("name", "")
        chain = token_data.get("chain", "")
        description = token_data.get("description", "")
        liquidity = token_data.get("liquidity", 0)
        market_cap = token_data.get("market_cap", 0)

        try:
            prompt = f"""你是一个加密货币风险分析师。请用中文为以下 AI Agent Token 写一句简短的风险提示（30字以内）。

项目: {name} (${symbol})
链: {chain}
市值: ${market_cap:,.0f}
流动性: ${liquidity:,.0f}
描述: {description}

评分: GitHub {scores['github']}/20, 社交 {scores['social']}/20, 安全 {scores['safety']}/20, 流动性 {scores['liquidity']}/20, 团队 {scores['team']}/20

请直接输出风险提示文字，不要任何前缀或格式。"""

            note = await self._call_llm(prompt, expect_number=False)
            if note:
                return note.strip()
        except Exception as e:
            print(f"[Scorer] Risk note error: {e}")

        return ""

    async def _call_llm(self, prompt: str, expect_number: bool = True) -> Optional[int | str]:
        """调用 DeepSeek LLM"""
        try:
            response = await self.llm_client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()

                if expect_number:
                    # 尝试从回复中提取数字
                    import re
                    numbers = re.findall(r'\d+', content)
                    if numbers:
                        return int(numbers[0])
                    return None
                else:
                    return content
            else:
                print(f"[Scorer] LLM API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"[Scorer] LLM call error: {e}")
            return None


async def run_scorer():
    """测试评分器"""
    scorer = AIScorer()
    try:
        test_token = {
            "address": "SoL111111111111111111111111111111111111111",
            "name": "AI Agent Protocol",
            "symbol": "AIA",
            "chain": "solana",
            "market_cap": 500000,
            "liquidity": 80000,
            "volume_24h": 120000,
            "description": "AI Agent Protocol - The first autonomous AI trading agent on Solana. Built by experienced team.",
        }
        result = await scorer.score_token(test_token)
        print(f"\nScore Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    finally:
        await scorer.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_scorer())
