from datetime import datetime

import httpx

from app.collectors.base import DataCollector


class TencentQuoteCollector(DataCollector):
    source_name = "tencent-qt"

    def __init__(self, codes: list[str]):
        self.codes = codes

    async def fetch(self):
        symbols = ",".join(self._to_tencent_symbol(code) for code in self.codes)
        if not symbols:
            return ""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://qt.gtimg.cn/q=" + symbols)
            response.raise_for_status()
            response.encoding = "gbk"
            return response.text

    def parse(self, raw):
        rows = []
        for line in raw.splitlines():
            if '="' not in line:
                continue
            payload = line.split('="', 1)[1].rstrip('";')
            fields = payload.split("~")
            if len(fields) > 38 and fields[2]:
                rows.append(fields)
        return rows

    def normalize(self, rows):
        normalized = []
        for fields in rows:
            exchange = "SH" if fields[0] == "1" else "SZ"
            quote_time = self._parse_quote_time(fields[30])
            latest_price = self._to_float(fields[3])
            previous_close = self._to_float(fields[4])
            normalized.append(
                {
                    "stock_code": f"{fields[2]}.{exchange}",
                    "name": fields[1],
                    "latest_price": latest_price,
                    "change_amount": self._to_float(fields[31]),
                    "change_percent": self._to_float(fields[32]),
                    "open_price": self._to_float(fields[5]),
                    "previous_close": previous_close,
                    "high_price": self._to_float(fields[33]),
                    "low_price": self._to_float(fields[34]),
                    "volume": self._to_float(fields[36]),
                    "turnover": self._to_float(fields[37]) * 10000 if self._to_float(fields[37]) is not None else None,
                    "source_name": self.source_name,
                    "confidence": "medium",
                    "delay_status": "public",
                    "quote_time": quote_time,
                }
            )
        return normalized

    def _to_tencent_symbol(self, code: str) -> str:
        digits, exchange = code.split(".", 1)
        prefix = "sh" if exchange.upper() == "SH" else "sz"
        return f"{prefix}{digits}"

    def _parse_quote_time(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y%m%d%H%M%S")

    def _to_float(self, value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
