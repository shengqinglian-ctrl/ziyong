from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CollectorResult:
    source_name: str
    records: list[dict[str, Any]]
    fetched_at: datetime
    ok: bool
    error: str | None = None


class DataCollector(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def validate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid_rows = []
        for row in rows:
            if row.get("stock_code") and row.get("latest_price") and row.get("quote_time"):
                valid_rows.append(row)
        return valid_rows

    async def health_check(self) -> bool:
        result = await self.run()
        return result.ok

    async def run(self) -> CollectorResult:
        try:
            raw = await self.fetch()
            parsed = self.parse(raw)
            normalized = self.normalize(parsed)
            valid_rows = self.validate(normalized)
            return CollectorResult(self.source_name, valid_rows, datetime.utcnow(), True)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            return CollectorResult(self.source_name, [], datetime.utcnow(), False, error)
