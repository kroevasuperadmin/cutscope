from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from .errors import ConfigurationError


class AttemptOutcome(StrEnum):
    SUCCESS = "success"
    REFUSED = "refused"
    ERROR = "error"
    TIMEOUT = "timeout"


class AdviceAction(StrEnum):
    RETRY_SAME = "RETRY_SAME"
    RETRY_REPHRASED = "RETRY_REPHRASED"
    ABANDON = "ABANDON"


@dataclass(frozen=True)
class Shot:
    id: str
    prompt: str
    reference_image_path: Path | None
    expected_duration_seconds: int
    character_ids: tuple[str, ...]
    max_attempts: int
    budget_ceiling_usd: Decimal
    difficulty: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ConfigurationError("Each shot needs a non-empty id.")
        if not self.prompt.strip():
            raise ConfigurationError(f"Shot {self.id!r} needs a non-empty prompt.")
        if self.expected_duration_seconds <= 0:
            raise ConfigurationError(f"Shot {self.id!r}: expected_duration_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ConfigurationError(f"Shot {self.id!r}: max_attempts must be positive.")
        if self.budget_ceiling_usd <= 0:
            raise ConfigurationError(f"Shot {self.id!r}: budget_ceiling_usd must be positive.")
        if self.difficulty is not None and not self.difficulty.strip():
            raise ConfigurationError(f"Shot {self.id!r}: difficulty must be a non-empty string when provided.")


@dataclass(frozen=True)
class Submission:
    operation: object
    operation_name: str


@dataclass(frozen=True)
class AttemptResult:
    outcome: AttemptOutcome
    operation_name: str | None
    asset_uri: str | None = None
    reason: str | None = None


@dataclass
class LiveShotMetrics:
    shot_id: str
    attempt_count: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    latencies_seconds: list[float] = field(default_factory=list)
    outcomes: list[AttemptOutcome] = field(default_factory=list)

    def record(self, outcome: AttemptOutcome, latency_seconds: float, estimated_cost_usd: Decimal) -> None:
        self.attempt_count += 1
        self.estimated_cost_usd += estimated_cost_usd
        self.latencies_seconds.append(latency_seconds)
        self.outcomes.append(outcome)

    @property
    def latest_outcome(self) -> AttemptOutcome | None:
        return self.outcomes[-1] if self.outcomes else None

    @property
    def latest_latency_seconds(self) -> float | None:
        return self.latencies_seconds[-1] if self.latencies_seconds else None

    def for_agent(self, next_attempt_estimated_usd: Decimal) -> dict[str, object]:
        outcome_counts = {outcome.value: self.outcomes.count(outcome) for outcome in AttemptOutcome}
        return {
            "shot_id": self.shot_id,
            "attempt_count": self.attempt_count,
            "estimated_cost_usd": float(self.estimated_cost_usd),
            "next_attempt_estimated_usd": float(next_attempt_estimated_usd),
            "latest_latency_seconds": self.latest_latency_seconds,
            "latest_outcome": self.latest_outcome.value if self.latest_outcome else None,
            "outcomes": outcome_counts,
        }


@dataclass(frozen=True)
class AgentAdvice:
    action: AdviceAction
    rationale: str
    replacement_prompt: str | None = None


@dataclass(frozen=True)
class Decision:
    action: AdviceAction
    rationale: str
    enforced_by_code: bool = False
    replacement_prompt: str | None = None


@dataclass(frozen=True)
class ShotRunResult:
    shot_id: str
    status: str
    attempts: int
    estimated_cost_usd: Decimal
    decision: str
    rationale: str
    asset_uri: str | None = None
