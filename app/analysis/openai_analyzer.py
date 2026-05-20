import json
from openai import OpenAI
from app.config import settings
from app.models import StockSnapshot, StockAnalysis
from app.analysis.local_fallback import local_analysis


ANALYSIS_SCHEMA = {
    "name": "stock_analysis",
    "schema": StockAnalysis.model_json_schema(),
    "strict": True,
}


def analyze_with_ai(snapshot: StockSnapshot, trigger_reasons: list[str] | None = None) -> StockAnalysis:
    if not settings.enable_openai_analysis or not settings.openai_api_key:
        return local_analysis(snapshot, trigger_reasons)

    client = OpenAI(api_key=settings.openai_api_key)
    payload = {
        "snapshot": snapshot.model_dump(),
        "trigger_reasons": trigger_reasons or [],
    }

    instructions = (
        "You are a stock market analysis assistant. "
        "Analyze only the provided JSON data. "
        "Do not invent prices, news, financial reports, analyst ratings, macro events, or company facts. "
        "When data is missing, explicitly mark it as uncertain. "
        "Explain why the stock may be rising or falling, its recent status, risk level, support, resistance, and next triggers. "
        "This is for information organization only and must not be personalized financial advice. "
        "Return valid JSON matching the schema."
    )

    try:
        response = client.responses.create(
            model=settings.openai_model,
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": ANALYSIS_SCHEMA["name"],
                    "schema": ANALYSIS_SCHEMA["schema"],
                    "strict": True,
                }
            },
        )
        data = json.loads(response.output_text)
        return StockAnalysis.model_validate(data)
    except Exception as exc:
        fallback = local_analysis(snapshot, trigger_reasons)
        fallback.move_explanation.uncertain_factors.append(f"OpenAI 分析失败，已使用本地规则兜底：{exc}")
        return fallback
