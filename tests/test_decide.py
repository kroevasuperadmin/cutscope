from decimal import Decimal

from cutscope.decision import enforce_decision
from cutscope.models import AdviceAction, AgentAdvice, AttemptOutcome, LiveShotMetrics, Shot


def test_budget_rule_overrides_gemini_retry_advice() -> None:
    shot = Shot(
        id="budget-test",
        prompt="An original, safe film shot.",
        reference_image_path=None,
        expected_duration_seconds=4,
        character_ids=("mara",),
        max_attempts=3,
        budget_ceiling_usd=Decimal("0.64"),
    )
    metrics = LiveShotMetrics(shot_id=shot.id)
    metrics.record(AttemptOutcome.ERROR, latency_seconds=1.0, estimated_cost_usd=Decimal("0.64"))

    decision = enforce_decision(
        AgentAdvice(AdviceAction.RETRY_SAME, "Gemini thinks another try may work."),
        shot,
        metrics,
        next_attempt_estimated_usd=Decimal("0.32"),
    )

    assert decision.action is AdviceAction.ABANDON
    assert decision.enforced_by_code is True
    assert "Budget" in decision.rationale
