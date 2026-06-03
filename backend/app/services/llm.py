import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import AnalysisCache


SYSTEM_PROMPT = (
    "你是一个A股行情监控系统里的分析助手。只基于输入的行情、提醒和公开信息摘要做简短分析，"
    "不得编造未提供的数据，不给出买卖指令，不承诺收益。输出中文，控制在220字以内。"
)

CHAT_SYSTEM_PROMPT = (
    "你是 A-Stock Watcher 的机器人助手。优先用中文回答用户问题。"
    "如果输入里包含系统提供的自选股、行情、资金流、提醒或信息中心上下文，只能基于这些上下文做分析，"
    "不要编造未提供的数据。可以解释功能、排查配置、总结公开信息，但不得给出买卖指令、收益承诺或确定性预测。"
)


class LLMError(Exception):
    pass


def model_status() -> dict[str, Any]:
    settings = get_settings()
    provider = settings.analysis_model_provider.lower()
    return {
        "provider": provider,
        "enabled": provider in {"local", "github"},
        "available_providers": [
            {"value": "local", "label": "本地 Ollama", "configured": True, "default_model": settings.local_model_name},
            {"value": "github", "label": "GitHub Models", "configured": bool(settings.github_models_token), "default_model": settings.github_models_model},
        ],
        "local_model": settings.local_model_name,
        "github_model": settings.github_models_model,
        "github_token_configured": bool(settings.github_models_token),
    }


def generate_analysis_summary(item: dict[str, Any]) -> str | None:
    settings = get_settings()
    provider = settings.analysis_model_provider.lower()
    if provider == "local":
        return _generate_with_ollama(item)
    if provider == "github":
        return _generate_with_github_models(item)
    return None


def generate_chat_answer(
    question: str,
    context: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str | None:
    settings = get_settings()
    provider = (provider or settings.analysis_model_provider).lower()
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": _chat_prompt(question, context or {})},
    ]
    if provider == "local":
        return _chat_with_ollama(messages, timeout=settings.chat_model_timeout_seconds, model=model, raise_errors=True)
    if provider == "github":
        return _chat_with_github_models(messages, timeout=settings.chat_model_timeout_seconds, model=model, raise_errors=True)
    return None


def generate_analysis_summary_cached(db: Session, item: dict[str, Any]) -> str | None:
    settings = get_settings()
    provider = settings.analysis_model_provider.lower()
    if provider not in {"local", "github"}:
        return None
    cache_key = _cache_key(item, provider)
    cutoff = datetime.utcnow() - timedelta(seconds=settings.analysis_cache_ttl_seconds)
    cached = (
        db.query(AnalysisCache)
        .filter(AnalysisCache.cache_key == cache_key, AnalysisCache.created_at >= cutoff)
        .one_or_none()
    )
    if cached:
        return cached.summary

    summary = generate_analysis_summary(item)
    if not summary:
        return None
    db.add(
        AnalysisCache(
            cache_key=cache_key,
            stock_code=item.get("stock_code") or "",
            provider=provider,
            model=_model_name(provider),
            summary=summary,
        )
    )
    db.flush()
    return summary


def _model_name(provider: str) -> str:
    settings = get_settings()
    if provider == "github":
        return settings.github_models_model
    return settings.local_model_name


def _cache_key(item: dict[str, Any], provider: str) -> str:
    material = {
        "provider": provider,
        "model": _model_name(provider),
        "stock_code": item.get("stock_code"),
        "quote_time": _json_value(item.get("quote_time")),
        "flow_time": _json_value((item.get("capital_flow") or {}).get("flow_time")),
        "change_percent": item.get("change_percent"),
        "heat_score": item.get("heat_score"),
        "stance": item.get("stance"),
        "drivers": item.get("drivers"),
        "risks": item.get("risks"),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _analysis_prompt(item: dict[str, Any]) -> str:
    sections = []
    for section in item.get("detailed_analysis") or []:
        lines = "；".join(section.get("items") or [])
        sections.append(f"{section.get('title')}：{lines}")
    return (
        f"股票：{item.get('name')} {item.get('stock_code')}\n"
        f"最新价：{item.get('latest_price')}，涨跌幅：{item.get('change_percent')}%，热度：{item.get('heat_score')}\n"
        f"系统判断：{item.get('stance')}\n"
        f"驱动：{'；'.join(item.get('drivers') or [])}\n"
        f"风险：{'；'.join(item.get('risks') or [])}\n"
        f"明细：{' | '.join(sections)}\n"
        "请按“核心结论、支撑证据、风险/观察点”给出一段面向监控看板的综合总结。"
    )


def _generate_with_ollama(item: dict[str, Any]) -> str | None:
    settings = get_settings()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _analysis_prompt(item)},
    ]
    return _chat_with_ollama(messages, temperature=0.2, timeout=settings.analysis_model_timeout_seconds)


def _chat_with_ollama(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    timeout: float | None = None,
    model: str | None = None,
    raise_errors: bool = False,
) -> str | None:
    settings = get_settings()
    url = settings.local_model_base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model or settings.local_model_name,
        "stream": False,
        "messages": messages,
        "options": {"temperature": temperature, "num_ctx": 1024, "num_predict": 256},
    }
    try:
        with httpx.Client(timeout=timeout or settings.analysis_model_timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        if raise_errors:
            raise LLMError(_http_error_message(exc)) from exc
        return None
    return ((data.get("message") or {}).get("content") or "").strip() or None


def _generate_with_github_models(item: dict[str, Any]) -> str | None:
    settings = get_settings()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _analysis_prompt(item)},
    ]
    return _chat_with_github_models(messages, temperature=0.2, max_tokens=320, timeout=settings.analysis_model_timeout_seconds)


def _chat_with_github_models(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 800,
    timeout: float | None = None,
    model: str | None = None,
    raise_errors: bool = False,
) -> str | None:
    settings = get_settings()
    if not settings.github_models_token:
        return None
    url = settings.github_models_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model or settings.github_models_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_models_token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    try:
        with httpx.Client(timeout=timeout or settings.analysis_model_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        if raise_errors:
            raise LLMError(_http_error_message(exc)) from exc
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    return ((choices[0].get("message") or {}).get("content") or "").strip() or None


def _chat_prompt(question: str, context: dict[str, Any]) -> str:
    if not context:
        return f"用户问题：{question}"
    context_json = json.dumps(context, ensure_ascii=False, default=_json_default)
    return (
        f"系统上下文 JSON：\n{context_json}\n\n"
        f"用户问题：{question}\n\n"
        "请结合上下文回答；如果上下文不足，明确说明缺少哪些信息。"
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "模型响应超时，请稍后重试或切换更快的模型"
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        text = response.text[:500]
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                text = error["message"]
            elif payload.get("detail"):
                text = str(payload["detail"])
        return f"模型服务返回 {response.status_code}: {text}"
    return f"模型服务连接失败: {exc}"
