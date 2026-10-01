"""Pydantic v2 data models for SIM-006 (PRD Section 5).

Defines the Event, EvaluationRequest, RuleEvaluationResult, and
EvaluationResponse models. All datetime fields must be timezone-aware UTC
per the Production Build Spec (Section 2); naive datetimes are rejected at
schema validation time.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class Event(BaseModel):
    """A synthetic event evaluated against the detection rules.

    Not every event type populates every field, so all fields except
    ``event_type`` are optional. Prior-state fields
    (``last_seen_sequence_number``, ``last_seen_timestamp``,
    ``prior_soc_percent``, ``charging_source_present``) are supplied by the
    caller so rules R-01 and R-08 can remain stateless (Blueprint 4.2).

    Attributes:
        event_type: One of "telemetry", "identity", "firmware", "cyber".
        timestamp: Event time (timezone-aware UTC), if present.
        voltage_v: Pack voltage in volts.
        temperature_c: Pack temperature in Celsius.
        soc_percent: State of charge, 0-100 percent.
        sequence_number: Monotonically increasing event sequence number.
        certificate_expiry: Certificate expiry time (timezone-aware UTC).
        firmware_hash: Observed firmware hash.
        expected_firmware_hash: Expected firmware hash for comparison.
        open_incident: Whether an open cyber incident is linked to the battery.
        prior_soc_percent: Previous state of charge reading, if known.
        charging_source_present: Whether a charging source was present.
        last_seen_sequence_number: Sequence number of the previous event.
        last_seen_timestamp: Timestamp of the previous event (timezone-aware UTC).
    """

    model_config = ConfigDict(frozen=True)

    event_type: Literal["telemetry", "identity", "firmware", "cyber"]
    timestamp: datetime | None = None
    voltage_v: float | None = None
    temperature_c: float | None = None
    soc_percent: float | None = None
    sequence_number: int | None = None
    certificate_expiry: datetime | None = None
    firmware_hash: str | None = None
    expected_firmware_hash: str | None = None
    open_incident: bool | None = None
    prior_soc_percent: float | None = None
    charging_source_present: bool | None = None
    last_seen_sequence_number: int | None = None
    last_seen_timestamp: datetime | None = None

    @field_validator("timestamp", "certificate_expiry", "last_seen_timestamp")
    @classmethod
    def _require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        """Reject naive datetimes (Build Spec Section 2).

        Args:
            value: The datetime value to validate.

        Returns:
            The unchanged timezone-aware datetime.

        Raises:
            ValueError: If the datetime has no timezone information.
        """
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must be timezone-aware (UTC, ISO 8601)")
        return value


class EvaluationRequest(BaseModel):
    """Request to evaluate one or more rules against a single event.

    Attributes:
        battery_id: Identifier of the battery the event belongs to.
        event: The event to evaluate.
        rule_ids: List of rule IDs (e.g. ["R-01", "R-02"]) or "all".
    """

    battery_id: str
    event: Event
    rule_ids: list[str] | Literal["all"]


class RuleEvaluationResult(BaseModel):
    """Outcome of a single rule evaluated against an event.

    Attributes:
        rule_id: Identifier of the evaluated rule, e.g. "R-01".
        rule_name: Human-readable name of the rule.
        result: Gate result: "PASS", "WARN", or "HARD_FAIL".
        detail: Human-readable explanation of the outcome.
    """

    rule_id: str
    rule_name: str
    result: Literal["PASS", "WARN", "HARD_FAIL"]
    detail: str


class EvaluationResponse(BaseModel):
    """Aggregated evaluation report for an event.

    Attributes:
        battery_id: Identifier of the battery the event belongs to.
        rules_evaluated: Number of rules that were evaluated.
        results: Per-rule evaluation outcomes.
        overall_gate: Worst result across all rules (HARD_FAIL > WARN > PASS).
        gate_reason: Explanation of the overall gate decision.
        simulated: Always True — marks the output as simulated (hard
            security requirement, PRD Section 13).
    """

    battery_id: str
    rules_evaluated: int
    results: list[RuleEvaluationResult]
    overall_gate: Literal["PASS", "WARN", "HARD_FAIL"]
    gate_reason: str
    simulated: bool = True


class ExplanationRequest(BaseModel):
    """Request body for explaining an already-computed evaluation."""

    evaluation: EvaluationResponse
