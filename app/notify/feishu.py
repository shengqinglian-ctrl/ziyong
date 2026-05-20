import httpx
from app.config import settings
from app.models import StockSnapshot, StockAnalysis


def build_card(snapshot: StockSnapshot, analysis: StockAnalysis, trigger_reasons: list[str]) -> dict:
    reasons = "\n".join([f"- {x}" for x in trigger_reasons]) or "- 手动分析"
    supporting = "\n".join([f"- {x}" for x in analysis.move_explanation.supporting_factors])
    risks = "\n".join([f"- {x}" for x in analysis.move_explanation.uncertain_factors])
    triggers = "\n".join([f"- {x}" for x in analysis.watch_next.triggers])

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue" if analysis.bias == "bullish" else "red" if analysis.bias == "bearish" else "grey",
                "title": {
                    "tag": "plain_text",
                    "content": f"{snapshot.symbol} 股票异动分析",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**当前价格**：{snapshot.current_price}\n"
                            f"**今日涨跌**：{snapshot.today_change_pct:.2f}%\n"
                            f"**成交量**：{snapshot.volume_vs_20d_avg:.2f}x 20日均量\n"
                            f"**AI观点**：{analysis.bias}，置信度 {analysis.confidence:.0%}"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**触发原因**：\n{reasons}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**为什么涨跌**：\n{analysis.move_explanation.main_reason}\n{supporting}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**近期状态**：\n{analysis.recent_status.summary}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**支撑位**：{', '.join(map(str, analysis.watch_next.support))}\n"
                            f"**压力位**：{', '.join(map(str, analysis.watch_next.resistance))}"
                        ),
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**不确定因素与风险**：\n{risks}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**接下来关注**：\n{triggers}",
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": analysis.disclaimer,
                        }
                    ],
                },
            ],
        },
    }


async def send_feishu_card(snapshot: StockSnapshot, analysis: StockAnalysis, trigger_reasons: list[str]) -> dict:
    if not settings.enable_feishu_push:
        return {"skipped": True, "reason": "ENABLE_FEISHU_PUSH=false"}

    if not settings.feishu_webhook_url:
        return {"skipped": True, "reason": "FEISHU_WEBHOOK_URL is empty"}

    payload = build_card(snapshot, analysis, trigger_reasons)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(settings.feishu_webhook_url, json=payload)
        response.raise_for_status()
        return response.json()
