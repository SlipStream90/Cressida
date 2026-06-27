from __future__ import annotations

from datetime import datetime
from typing import Any


class MetricsCollector:
    def __init__(self) -> None:
        self._metrics: dict[str, list[dict[str, Any]]] = {}

    def record(self, category: str, **data: Any) -> None:
        self._metrics.setdefault(category, []).append({
            "timestamp": datetime.now().isoformat(),
            **data,
        })

    def get_category(self, category: str) -> list[dict[str, Any]]:
        return list(self._metrics.get(category, []))

    def summarize(self, category: str) -> dict[str, Any]:
        records = self._metrics.get(category, [])
        if not records:
            return {"count": 0}

        numeric_fields: dict[str, list[float]] = {}
        for record in records:
            for key, value in record.items():
                if isinstance(value, (int, float)):
                    numeric_fields.setdefault(key, []).append(float(value))

        summary: dict[str, Any] = {"count": len(records)}
        for field, values in numeric_fields.items():
            if values:
                summary[f"{field}_avg"] = sum(values) / len(values)
                summary[f"{field}_min"] = min(values)
                summary[f"{field}_max"] = max(values)

        return summary

    def get_all_categories(self) -> dict[str, Any]:
        return {cat: self.summarize(cat) for cat in self._metrics}

    def clear(self) -> None:
        self._metrics.clear()
