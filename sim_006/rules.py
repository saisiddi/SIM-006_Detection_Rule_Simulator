"""Detection rule handlers and rule registry for SIM-006 (PRD Section 6).

Each rule (R-01 through R-08) is an independent, pure function that reads an
Event and returns a RuleEvaluationResult — handlers never mutate input state.
All numeric thresholds come from :mod:`sim_006.constants` (Build Spec 1).
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sim_006.constants import (
    REPLAY_MAX_FUTURE_SKEW_SECONDS,
    REPLAY_STALENESS_WINDOW_SECONDS,
    SOC_JUMP_THRESHOLD_PCT,
    TEMP_ESCALATION_PCT,
    TEMP_SAFE_MAX,
    TEMP_SAFE_MIN,
    VOLTAGE_ESCALATION_PCT,
    VOLTAGE_SAFE_MAX,
    VOLTAGE_SAFE_MIN,
)
from sim_006.models import Event, RuleEvaluationResult

INSUFFICIENT_CONTEXT_DETAIL = (
    "Insufficient prior-state context to evaluate — treated as first-seen event"
)


def _utcnow() -> datetime:
    """Return the current evaluation time in UTC.

    Returns:
        Current time as a timezone-aware datetime. Wrapped in a function so
        tests can monkeypatch the clock deterministically.
    """
    return datetime.now(timezone.utc)


def _insufficient(rule_id: str, rule_name: str) -> RuleEvaluationResult:
    """Build the standard insufficient-context PASS result.

    Args:
        rule_id: Identifier of the rule.
        rule_name: Human-readable name of the rule.

    Returns:
        A PASS result with the Build Spec Section 3 detail wording.
    """
    return RuleEvaluationResult(
        rule_id=rule_id, rule_name=rule_name, result="PASS", detail=INSUFFICIENT_CONTEXT_DETAIL
    )


def evaluate_r01(event: Event) -> RuleEvaluationResult:
    """R-01: Replay attack detected.

    HARD_FAIL if ``sequence_number`` duplicates ``last_seen_sequence_number``,
    or if ``timestamp`` is more than REPLAY_STALENESS_WINDOW_SECONDS older
    than the current evaluation time, more than REPLAY_MAX_FUTURE_SKEW_SECONDS
    ahead of it, or older than ``last_seen_timestamp``.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-01"
    rule_name = "Replay attack detected"

    has_sequence_context = (
        event.sequence_number is not None and event.last_seen_sequence_number is not None
    )
    if event.timestamp is None and not has_sequence_context:
        return _insufficient(rule_id, rule_name)

    if has_sequence_context and event.sequence_number == event.last_seen_sequence_number:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail=(
                f"Duplicate sequence_number {event.sequence_number} " "(matches last seen value)"
            ),
        )

    if event.timestamp is not None:
        now = _utcnow()
        if now - event.timestamp > timedelta(seconds=REPLAY_STALENESS_WINDOW_SECONDS):
            age = (now - event.timestamp).total_seconds()
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="HARD_FAIL",
                detail=(
                    f"Timestamp is stale: {age:.0f}s older than evaluation time "
                    f"(window {REPLAY_STALENESS_WINDOW_SECONDS}s)"
                ),
            )
        if event.timestamp - now > timedelta(seconds=REPLAY_MAX_FUTURE_SKEW_SECONDS):
            lead = (event.timestamp - now).total_seconds()
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="HARD_FAIL",
                detail=(
                    f"Timestamp is in the future: {lead:.0f}s ahead of evaluation time "
                    f"(skew window {REPLAY_MAX_FUTURE_SKEW_SECONDS}s)"
                ),
            )
        if event.last_seen_timestamp is not None and event.timestamp < event.last_seen_timestamp:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="HARD_FAIL",
                detail="Timestamp is older than the last seen timestamp",
            )

    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        result="PASS",
        detail="No replay indicators detected",
    )


def evaluate_r02(event: Event) -> RuleEvaluationResult:
    """R-02: Missing telemetry timestamp.

    HARD_FAIL if ``timestamp`` is null on a telemetry event.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-02"
    rule_name = "Missing telemetry timestamp"

    if event.timestamp is not None:
        return RuleEvaluationResult(
            rule_id=rule_id, rule_name=rule_name, result="PASS", detail="timestamp present"
        )
    if event.event_type == "telemetry":
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail="timestamp field is null",
        )
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        result="PASS",
        detail=f"timestamp null but event_type is {event.event_type}, not telemetry",
    )


def evaluate_r03(event: Event) -> RuleEvaluationResult:
    """R-03: Invalid or expired certificate.

    HARD_FAIL if ``certificate_expiry`` is in the past, or if the certificate
    is missing on an identity event.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-03"
    rule_name = "Invalid or expired certificate"

    if event.certificate_expiry is None:
        if event.event_type == "identity":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="HARD_FAIL",
                detail="certificate missing on identity event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"no certificate on {event.event_type} event (not required)",
        )

    if event.certificate_expiry < _utcnow():
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail="certificate_expiry is in the past",
        )
    return RuleEvaluationResult(
        rule_id=rule_id, rule_name=rule_name, result="PASS", detail="certificate valid"
    )


def evaluate_r04(event: Event) -> RuleEvaluationResult:
    """R-04: Firmware hash mismatch.

    HARD_FAIL if ``firmware_hash`` differs from ``expected_firmware_hash``, or
    if either hash is missing on a firmware event (fail closed).

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-04"
    rule_name = "Firmware hash mismatch"

    if event.firmware_hash is None or event.expected_firmware_hash is None:
        if event.event_type == "firmware":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="HARD_FAIL",
                detail="firmware hash missing on firmware event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"no firmware hashes on {event.event_type} event (not required)",
        )

    if event.firmware_hash != event.expected_firmware_hash:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail="firmware_hash does not match expected_firmware_hash",
        )
    return RuleEvaluationResult(
        rule_id=rule_id, rule_name=rule_name, result="PASS", detail="firmware hash matches"
    )


def evaluate_r05(event: Event) -> RuleEvaluationResult:
    """R-05: Voltage out of range (48V pack).

    PASS within VOLTAGE_SAFE_MIN..VOLTAGE_SAFE_MAX; WARN within
    VOLTAGE_ESCALATION_PCT of a boundary; HARD_FAIL beyond that.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-05"
    rule_name = "Voltage out of range"

    if event.voltage_v is None:
        if event.event_type == "telemetry":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="WARN",
                detail="voltage_v missing on telemetry event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"voltage_v not applicable to {event.event_type} event",
        )

    voltage = event.voltage_v
    warn_min = VOLTAGE_SAFE_MIN * (1 - VOLTAGE_ESCALATION_PCT)
    warn_max = VOLTAGE_SAFE_MAX * (1 + VOLTAGE_ESCALATION_PCT)

    if VOLTAGE_SAFE_MIN <= voltage <= VOLTAGE_SAFE_MAX:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=(
                f"Voltage {voltage:g}V within " f"{VOLTAGE_SAFE_MIN:g}-{VOLTAGE_SAFE_MAX:g}V range"
            ),
        )
    if warn_min <= voltage <= warn_max:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="WARN",
            detail=(
                f"Voltage {voltage:g}V outside "
                f"{VOLTAGE_SAFE_MIN:g}-{VOLTAGE_SAFE_MAX:g}V range "
                f"but within +/-{VOLTAGE_ESCALATION_PCT:.0%} escalation band"
            ),
        )
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        result="HARD_FAIL",
        detail=(
            f"Voltage {voltage:g}V beyond +/-{VOLTAGE_ESCALATION_PCT:.0%} escalation band "
            f"(outside {warn_min:g}-{warn_max:g}V)"
        ),
    )


def evaluate_r06(event: Event) -> RuleEvaluationResult:
    """R-06: Critical temperature.

    PASS within TEMP_SAFE_MIN..TEMP_SAFE_MAX; WARN within TEMP_ESCALATION_PCT
    of a boundary; HARD_FAIL beyond that (mirrors R-05).

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-06"
    rule_name = "Critical temperature"

    if event.temperature_c is None:
        if event.event_type == "telemetry":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="WARN",
                detail="temperature_c missing on telemetry event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"temperature_c not applicable to {event.event_type} event",
        )

    temperature = event.temperature_c
    warn_min = TEMP_SAFE_MIN * (1 + TEMP_ESCALATION_PCT)
    warn_max = TEMP_SAFE_MAX * (1 + TEMP_ESCALATION_PCT)

    if TEMP_SAFE_MIN <= temperature <= TEMP_SAFE_MAX:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=(
                f"Temperature {temperature:g}C within "
                f"{TEMP_SAFE_MIN:g}-{TEMP_SAFE_MAX:g}C range"
            ),
        )
    if warn_min <= temperature <= warn_max:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="WARN",
            detail=(
                f"Temperature {temperature:g}C outside "
                f"{TEMP_SAFE_MIN:g}-{TEMP_SAFE_MAX:g}C range "
                f"but within +/-{TEMP_ESCALATION_PCT:.0%} escalation band"
            ),
        )
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        result="HARD_FAIL",
        detail=(
            f"Temperature {temperature:g}C beyond +/-{TEMP_ESCALATION_PCT:.0%} "
            f"escalation band (outside {warn_min:g}-{warn_max:g}C)"
        ),
    )


def evaluate_r07(event: Event) -> RuleEvaluationResult:
    """R-07: Open cyber incident linked to battery.

    HARD_FAIL if ``open_incident`` is True.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-07"
    rule_name = "Open cyber incident linked to battery"

    if event.open_incident is True:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail="open_incident is true",
        )
    if event.open_incident is None:
        if event.event_type == "telemetry":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="WARN",
                detail="open_incident missing on telemetry event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"open_incident not applicable to {event.event_type} event",
        )
    return RuleEvaluationResult(
        rule_id=rule_id, rule_name=rule_name, result="PASS", detail="no open incident"
    )


def evaluate_r08(event: Event) -> RuleEvaluationResult:
    """R-08: Physically impossible telemetry.

    HARD_FAIL if ``soc_percent`` increased by more than SOC_JUMP_THRESHOLD_PCT
    points over ``prior_soc_percent`` while ``charging_source_present`` is
    False.

    Args:
        event: The event to evaluate.

    Returns:
        The rule evaluation result.
    """
    rule_id = "R-08"
    rule_name = "Physically impossible telemetry"

    if event.prior_soc_percent is None:
        return _insufficient(rule_id, rule_name)
    if event.soc_percent is None:
        if event.event_type == "telemetry":
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                result="WARN",
                detail="soc_percent missing on telemetry event",
            )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="PASS",
            detail=f"soc_percent not applicable to {event.event_type} event",
        )

    jump = event.soc_percent - event.prior_soc_percent
    if jump > SOC_JUMP_THRESHOLD_PCT and event.charging_source_present is not True:
        source = (
            "charging_source_present is false"
            if event.charging_source_present is False
            else "charging_source_present unknown"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            result="HARD_FAIL",
            detail=(
                f"SOC jumped {jump:g}% without charging source ({source}; "
                f"threshold {SOC_JUMP_THRESHOLD_PCT:g}%)"
            ),
        )
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        result="PASS",
        detail=f"SOC jump {jump:g}% within physical limits",
    )


class RuleDefinition(NamedTuple):
    """Contract between the rule registry and the rule engine (Blueprint 4.1).

    Attributes:
        rule_id: Unique rule identifier, e.g. "R-01".
        rule_name: Human-readable rule name.
        handler: Pure function mapping an Event to a RuleEvaluationResult.
        description: Rule description with thresholds, surfaced by GET /rules
            and the list-rules CLI command.
    """

    rule_id: str
    rule_name: str
    handler: Callable[[Event], RuleEvaluationResult]
    description: str


RULE_REGISTRY: dict[str, RuleDefinition] = {
    "R-01": RuleDefinition(
        "R-01",
        "Replay attack detected",
        evaluate_r01,
        f"HARD_FAIL if timestamp is >{REPLAY_STALENESS_WINDOW_SECONDS}s older than "
        f"evaluation time or >{REPLAY_MAX_FUTURE_SKEW_SECONDS}s ahead of it, or "
        "older than last_seen_timestamp, or sequence_number duplicates "
        "last_seen_sequence_number",
    ),
    "R-02": RuleDefinition(
        "R-02",
        "Missing telemetry timestamp",
        evaluate_r02,
        "HARD_FAIL if timestamp is null on a telemetry event",
    ),
    "R-03": RuleDefinition(
        "R-03",
        "Invalid or expired certificate",
        evaluate_r03,
        "HARD_FAIL if certificate_expiry is in the past or certificate is missing "
        "on an identity event",
    ),
    "R-04": RuleDefinition(
        "R-04",
        "Firmware hash mismatch",
        evaluate_r04,
        "HARD_FAIL if firmware_hash != expected_firmware_hash or hashes are missing "
        "on a firmware event",
    ),
    "R-05": RuleDefinition(
        "R-05",
        "Voltage out of range",
        evaluate_r05,
        f"PASS {VOLTAGE_SAFE_MIN:g}-{VOLTAGE_SAFE_MAX:g}V; "
        f"WARN within +/-{VOLTAGE_ESCALATION_PCT:.0%} of a boundary; HARD_FAIL beyond",
    ),
    "R-06": RuleDefinition(
        "R-06",
        "Critical temperature",
        evaluate_r06,
        f"PASS {TEMP_SAFE_MIN:g}-{TEMP_SAFE_MAX:g}C; "
        f"WARN within +/-{TEMP_ESCALATION_PCT:.0%} of a boundary; HARD_FAIL beyond",
    ),
    "R-07": RuleDefinition(
        "R-07",
        "Open cyber incident linked to battery",
        evaluate_r07,
        "HARD_FAIL if open_incident is true",
    ),
    "R-08": RuleDefinition(
        "R-08",
        "Physically impossible telemetry",
        evaluate_r08,
        f"HARD_FAIL if soc_percent increases by >{SOC_JUMP_THRESHOLD_PCT:g} points "
        "over prior_soc_percent without a charging source (false or unknown)",
    ),
}
