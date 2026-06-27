from __future__ import annotations

from typing import Any


class ScoreWeights:
    def __init__(
        self,
        architecture_compliance: float = 0.3,
        code_quality: float = 0.2,
        test_coverage: float = 0.2,
        performance: float = 0.15,
        security: float = 0.15,
    ) -> None:
        total = architecture_compliance + code_quality + test_coverage + performance + security
        self.architecture_compliance = architecture_compliance / total
        self.code_quality = code_quality / total
        self.test_coverage = test_coverage / total
        self.performance = performance / total
        self.security = security / total


DEFAULT_WEIGHTS = ScoreWeights()


class Scorer:
    def __init__(self, weights: ScoreWeights | None = None) -> None:
        self._weights = weights or DEFAULT_WEIGHTS

    def score_task(
        self,
        architecture_compliance: float = 1.0,
        code_quality: float = 1.0,
        test_coverage: float = 1.0,
        performance: float = 1.0,
        security: float = 1.0,
    ) -> float:
        w = self._weights
        return (
            w.architecture_compliance * architecture_compliance
            + w.code_quality * code_quality
            + w.test_coverage * test_coverage
            + w.performance * performance
            + w.security * security
        )

    def score_mission(self, task_scores: list[float]) -> float:
        if not task_scores:
            return 0.0
        return sum(task_scores) / len(task_scores)

    def score_with_details(
        self,
        architecture_compliance: float = 1.0,
        code_quality: float = 1.0,
        test_coverage: float = 1.0,
        performance: float = 1.0,
        security: float = 1.0,
    ) -> dict[str, Any]:
        total = self.score_task(
            architecture_compliance=architecture_compliance,
            code_quality=code_quality,
            test_coverage=test_coverage,
            performance=performance,
            security=security,
        )
        return {
            "total": round(total, 4),
            "details": {
                "architecture_compliance": architecture_compliance,
                "code_quality": code_quality,
                "test_coverage": test_coverage,
                "performance": performance,
                "security": security,
            },
            "weights": {
                "architecture_compliance": self._weights.architecture_compliance,
                "code_quality": self._weights.code_quality,
                "test_coverage": self._weights.test_coverage,
                "performance": self._weights.performance,
                "security": self._weights.security,
            },
        }
