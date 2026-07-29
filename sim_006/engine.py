"""Rule engine for SIM-006 (PRD Sections 6 and 9).

Thin orchestrator: resolves requested rule IDs against RULE_REGISTRY, runs
each rule handler, and aggregates the worst-result-wins gate decision
(HARD_FAIL > WARN > PASS). Stateless per evaluation call and read-only.
"""

import logging
from typing import Literal

from sim_006.models import EvaluationRequest, EvaluationResponse, RuleEvaluationResult
from sim_006.rules import RULE_REGISTRY

logger = logging.getLogger(__name__)

_SEVERITY_RANK: dict[str, int] = {"PASS": 0, "WARN": 1, "HARD_FAIL": 2}


class RuleSelectionError(ValueError):
    """A rule selection in an evaluation request is invalid.

    Carries a Build Spec Section 4 style error payload for the API and CLI
    layers to surface.

    Attributes:
        error: Machine-readable error code.
        detail: Human-readable explanation.
    """

    def __init__(self, error: str, detail: str) -> None:
        """Initialise the error with its code and detail message.

        Args:
            error: Machine-readable error code, e.g. "unknown_rule_id".
            detail: Human-readable explanation of the failure.
        """
        super().__init__(detail)
        self.error = error
        self.detail = detail

    @property
    def payload(self) -> dict[str, object]:
        """Serialise the error in the Build Spec Section 4 format.

        Returns:
            The error payload, always tagged simulated=True.
        """
        return {"error": self.error, "detail": self.detail, "simulated": True}


def _unknown_rule_error(rule_id: str) -> RuleSelectionError:
    """Build the unknown-rule-ID error (Build Spec Section 4).

    Args:
        rule_id: The offending rule ID from the request.

    Returns:
        The populated RuleSelectionError.
    """
    return RuleSelectionError(
        "unknown_rule_id",
        f"Rule ID '{rule_id}' not found. Valid rule IDs: {', '.join(RULE_REGISTRY)}",
    )


class RuleEngine:
    """Orchestrates rule evaluation and gate aggregation.

    The engine holds no state between calls: every rule receives the caller-
    supplied prior-state fields inside the event itself (Blueprint 4.2).
    """

    def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        """Evaluate the requested rules against the event and aggregate the gate.

        Args:
            request: The evaluation request (battery_id, event, rule IDs).

        Returns:
            The evaluation response with per-rule results, the worst-result-wins
            overall gate, and simulated=True.

        Raises:
            RuleSelectionError: If rule_ids is empty or contains an unknown
                rule ID.
        """
        rule_ids = self._resolve_rule_ids(request.rule_ids)
        results = [RULE_REGISTRY[rule_id].handler(request.event) for rule_id in rule_ids]
        overall_gate, gate_reason = self._aggregate(results, rule_ids)
        return EvaluationResponse(
            battery_id=request.battery_id,
            rules_evaluated=len(results),
            results=results,
            overall_gate=overall_gate,
            gate_reason=gate_reason,
        )

    @staticmethod
    def _resolve_rule_ids(rule_ids: list[str] | Literal["all"]) -> list[str]:
        """Resolve and validate the requested rule IDs against RULE_REGISTRY.

        Args:
            rule_ids: "all" or an explicit list of rule IDs.

        Returns:
            The ordered list of rule IDs to evaluate.

        Raises:
            RuleSelectionError: If the list is empty or contains an unknown ID.
        """
        if rule_ids == "all":
            return list(RULE_REGISTRY)
        if not rule_ids:
            raise RuleSelectionError(
                "empty_rule_selection",
                "rule_ids must contain at least one rule ID or be 'all'",
            )
        for rule_id in rule_ids:
            if rule_id not in RULE_REGISTRY:
                raise _unknown_rule_error(rule_id)
        return list(rule_ids)

    @staticmethod
    def _aggregate(
        results: list[RuleEvaluationResult], rule_ids: list[str]
    ) -> tuple[Literal["PASS", "WARN", "HARD_FAIL"], str]:
        """Aggregate per-rule results into the overall gate decision.

        Worst result wins (HARD_FAIL > WARN > PASS). Rules not selected are
        treated as bypassed: they do not count toward the gate and the bypass
        is logged (PRD Section 6), never silent and never in gate_reason so
        that PRD Section 11 output matches exactly.

        Args:
            results: Per-rule evaluation results, non-empty.
            rule_ids: The resolved rule IDs that were evaluated.

        Returns:
            The overall gate and its human-readable reason.
        """
        worst_result = max(results, key=lambda result: _SEVERITY_RANK[result.result]).result
        triggers = [result for result in results if result.result == worst_result]

        if worst_result == "PASS":
            gate_reason = f"All {len(results)} rules passed"
        elif len(triggers) == 1:
            gate_reason = f"Rule {triggers[0].rule_id} triggered {worst_result}"
        else:
            gate_reason = (
                f"Rules {', '.join(trigger.rule_id for trigger in triggers)} "
                f"triggered {worst_result}"
            )

        excluded = sorted(set(RULE_REGISTRY) - set(rule_ids))
        if excluded:
            logger.warning(
                "Excluded rules %s (bypassed) did not count toward the gate decision",
                ", ".join(excluded),
            )
        return worst_result, gate_reason
