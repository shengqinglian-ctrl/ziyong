from datetime import datetime
from random import random

from app.collectors.base import DataCollector


class MockQuoteCollector(DataCollector):
    source_name = "mock-public-page"

    def __init__(self, codes: list[str]):
        self.codes = codes

    async def fetch(self):
        return [{"code": code, "price": round(10 + random() * 90, 2)} for code in self.codes]

    def parse(self, raw):
        return raw

    def normalize(self, rows):
        now = datetime.utcnow()
        return [
            {
                "stock_code": row["code"],
                "name": row["code"],
                "latest_price": row["price"],
                "change_amount": None,
                "change_percent": round((random() - 0.5) * 8, 2),
                "volume": round(random() * 10_000_000, 0),
                "turnover": round(random() * 500_000_000, 0),
                "source_name": self.source_name,
                "confidence": "low",
                "delay_status": "mock",
                "quote_time": now,
            }
            for row in rows
        ]
