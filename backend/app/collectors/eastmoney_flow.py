import asyncio
from datetime import datetime
from typing import Any

import httpx

from app.collectors.base import DataCollector


class EastmoneyCapitalFlowCollector(DataCollector):
    source_name = "eastmoney-flow"

    def __init__(self, codes: list[str]):
        self.codes = codes

    async def fetch(self) -> list[dict[str, Any]]:
        if not self.codes:
            return []
        fields = ",".join(
            [
                "f57",
                "f58",
                "f62",
                "f66",
                "f69",
                "f72",
                "f75",
                "f78",
                "f81",
                "f84",
                "f87",
                "f164",
                "f165",
                "f184",
            ]
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=4, headers=headers, trust_env=False) as client:
            results = await asyncio.gather(
                *(self._fetch_one(client, code, fields) for code in self.codes),
                return_exceptions=True,
            )
        rows = []
        errors = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result) or result.__class__.__name__)
            else:
                rows.append(result)
        if not rows and errors:
            raise RuntimeError("; ".join(errors))
        return rows

    async def _fetch_one(self, client: httpx.AsyncClient, code: str, fields: str) -> dict[str, Any]:
        try:
            response = await asyncio.wait_for(
                client.get(
                    "https://push2.eastmoney.com/api/qt/stock/get"
                    f"?secid={self._to_secid(code)}&fields={fields}",
                ),
                timeout=5,
            )
            response.raise_for_status()
            return {"stock_code": code, "payload": response.json()}
        except Exception as exc:
            raise RuntimeError(f"{code}: {str(exc) or exc.__class__.__name__}") from exc

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for row in raw:
            data = (row.get("payload") or {}).get("data") or {}
            if data:
                rows.append({"stock_code": row["stock_code"], "data": data})
        return rows

    def normalize(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        normalized = []
        for row in rows:
            data = row["data"]
            normalized.append(
                {
                    "stock_code": row["stock_code"],
                    "name": data.get("f58") or row["stock_code"],
                    "main_net_inflow": self._to_float(data.get("f62")),
                    "main_net_ratio": self._to_float(data.get("f184")),
                    "super_large_net_inflow": self._to_float(data.get("f66")),
                    "super_large_net_ratio": self._to_float(data.get("f69")),
                    "large_net_inflow": self._to_float(data.get("f72")),
                    "large_net_ratio": self._to_float(data.get("f75")),
                    "medium_net_inflow": self._to_float(data.get("f78")),
                    "medium_net_ratio": self._to_float(data.get("f81")),
                    "small_net_inflow": self._to_float(data.get("f84")),
                    "small_net_ratio": self._to_float(data.get("f87")),
                    "five_day_main_net_inflow": self._to_float(data.get("f164")),
                    "five_day_main_net_ratio": self._to_float(data.get("f165")),
                    "source_name": self.source_name,
                    "confidence": "medium",
                    "flow_time": now,
                }
            )
        return normalized

    def validate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("stock_code") and row.get("flow_time")]

    def _to_secid(self, code: str) -> str:
        digits, exchange = code.split(".", 1)
        market = "1" if exchange.upper() == "SH" else "0"
        return f"{market}.{digits}"

    def _to_float(self, value: Any) -> float | None:
        if value in (None, "", "-"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
