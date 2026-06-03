from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.models.domain import AlertRule, QuoteSnapshot


@dataclass
class RuleDecision:
    triggered: bool
    title: str
    message: str
    payload: dict[str, Any]


class RuleEngine:
    def __init__(self):
        self._last_triggered: dict[int, datetime] = {}

    def evaluate_quote(
        self,
        rule: AlertRule,
        quote: QuoteSnapshot,
        previous_quote: QuoteSnapshot | None = None,
    ) -> RuleDecision:
        if not rule.enabled:
            return self._no(rule, quote)
        last = self._last_triggered.get(rule.id)
        if last and datetime.utcnow() - last < timedelta(seconds=rule.cooldown_seconds):
            return self._no(rule, quote)

        triggered = self._matches(rule, quote)

        if not triggered:
            return self._no(rule, quote)
        if previous_quote and self._matches(rule, previous_quote) and not self._alert_value_changed(rule, quote, previous_quote):
            return self._no(rule, quote)

        self._last_triggered[rule.id] = datetime.utcnow()
        title = f"{quote.name} {rule.name}"
        message = (
            f"股票：{quote.name} {quote.stock_code}\n"
            f"触发规则：{rule.name}\n"
            f"当前价格：{quote.latest_price}\n"
            f"涨跌幅：{quote.change_percent}%\n"
            f"数据源：{quote.source_name}\n"
            f"更新时间：{quote.quote_time:%Y-%m-%d %H:%M:%S}\n"
            "提示：本提醒仅基于公开信息和用户规则生成，不构成投资建议。"
        )
        return RuleDecision(True, title, message, {"quote_id": quote.id, "rule_id": rule.id})

    def _matches(self, rule: AlertRule, quote: QuoteSnapshot) -> bool:
        rule_type = rule.rule_type
        params = rule.params or {}
        value = float(params["value"])
        if rule_type == "price_above":
            return quote.latest_price > value
        if rule_type == "price_below":
            return quote.latest_price < value
        if rule_type == "change_percent_above" and quote.change_percent is not None:
            return quote.change_percent > value
        if rule_type == "change_percent_below" and quote.change_percent is not None:
            return quote.change_percent < value
        if rule_type == "turnover_above" and quote.turnover is not None:
            return quote.turnover > value
        return False

    def _alert_value_changed(self, rule: AlertRule, quote: QuoteSnapshot, previous_quote: QuoteSnapshot) -> bool:
        current_value = self._alert_value(rule, quote)
        previous_value = self._alert_value(rule, previous_quote)
        if current_value is None or previous_value is None:
            return current_value != previous_value
        return abs(current_value - previous_value) > 1e-9

    def _alert_value(self, rule: AlertRule, quote: QuoteSnapshot) -> float | None:
        if rule.rule_type in {"price_above", "price_below"}:
            return quote.latest_price
        if rule.rule_type in {"change_percent_above", "change_percent_below"}:
            return quote.change_percent
        if rule.rule_type == "turnover_above":
            return quote.turnover
        return None

    def _no(self, rule: AlertRule, quote: QuoteSnapshot) -> RuleDecision:
        return RuleDecision(False, "", "", {"rule_id": rule.id, "quote_id": quote.id})
