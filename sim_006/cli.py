"""Command-line interface for SIM-006 (PRD Section 10.1).

Implements ``evaluate`` and ``list-rules``. The --event file holds a full
evaluation request object ({battery_id, event, rule_ids?}); --rules overrides
the file's rule_ids and is required if the file omits them. Errors are
printed to stderr with a non-zero exit code — never a stack trace
(Build Spec Section 4).
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.explanation import configured_explanation_service
from sim_006.models import EvaluationRequest
from sim_006.rules import RULE_REGISTRY

logger = logging.getLogger(__name__)


class CliError(Exception):
    """A user-facing CLI failure; message printed to stderr, exit code 1."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the SIM-006 CLI.

    Returns:
        Configured ArgumentParser with evaluate and list-rules subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="sim_006",
        description="SIM-006 Detection Rule Simulator (all output is simulated)",
    )
    subparsers = parser.add_subparsers(dest="command")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Evaluate detection rules against an event JSON file"
    )
    evaluate_parser.add_argument(
        "--event", required=True, help="Path to evaluation request JSON file"
    )
    evaluate_parser.add_argument(
        "--rules",
        help="Comma-separated rule IDs (e.g. R-01,R-02,R-05) or 'all'. "
        "Overrides rule_ids in the event file",
    )

    subparsers.add_parser("list-rules", help="List all 8 detection rules and thresholds")
    explain_parser = subparsers.add_parser(
        "explain", help="Explain a deterministic evaluation from a request JSON file"
    )
    explain_parser.add_argument(
        "--event", required=True, help="Path to evaluation request JSON file"
    )

    return parser


def _parse_rules_arg(rules_arg: str) -> list[str] | str:
    """Parse the --rules flag value into rule IDs or 'all'.

    Args:
        rules_arg: Comma-separated rule IDs or "all".

    Returns:
        "all" or the list of rule IDs.
    """
    if rules_arg.strip() == "all":
        return "all"
    return [part.strip() for part in rules_arg.split(",") if part.strip()]


def _load_request(event_path: str, rules_arg: str | None) -> EvaluationRequest:
    """Load and validate the evaluation request from a JSON file.

    Args:
        event_path: Path to the request JSON file ({battery_id, event, rule_ids?}).
        rules_arg: Optional --rules flag value, overriding the file's rule_ids.

    Returns:
        The validated EvaluationRequest.

    Raises:
        CliError: If the file is unreadable, not JSON, not an object, missing
            rule IDs, or fails schema validation.
    """
    try:
        raw = Path(event_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read event file '{event_path}': {exc.strerror}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"event file '{event_path}' is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"event file '{event_path}' must contain a JSON object")

    if rules_arg is not None:
        payload["rule_ids"] = _parse_rules_arg(rules_arg)
    elif "rule_ids" not in payload:
        raise CliError("no rules specified: pass --rules or include rule_ids in the event file")

    try:
        return EvaluationRequest.model_validate(payload)
    except ValidationError as exc:
        raise CliError(f"invalid evaluation request: {exc}") from exc


def _cmd_evaluate(event_path: str, rules_arg: str | None) -> int:
    """Run the evaluate subcommand.

    Args:
        event_path: Path to the request JSON file.
        rules_arg: Optional --rules flag value.

    Returns:
        Exit code: 0 on success, 1 on any error.
    """
    try:
        request = _load_request(event_path, rules_arg)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        response = RuleEngine().evaluate(request)
    except RuleSelectionError as exc:
        print(json.dumps(exc.payload), file=sys.stderr)
        return 1

    print(response.model_dump_json(indent=2))
    return 0


def _cmd_list_rules() -> int:
    """Run the list-rules subcommand: all 8 rule definitions and thresholds.

    Returns:
        Exit code 0.
    """
    for definition in RULE_REGISTRY.values():
        print(f"{definition.rule_id} - {definition.rule_name}")
        print(f"    {definition.description}")
    return 0


def _cmd_explain(event_path: str) -> int:
    """Evaluate a request and print its structured explanation."""
    try:
        request = _load_request(event_path, None)
        evaluation = RuleEngine().evaluate(request)
        explanation = configured_explanation_service().explain(evaluation)
    except (CliError, RuleSelectionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(explanation.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Process exit code (0 on success, non-zero on error).
    """
    logging.basicConfig(
        stream=sys.stderr, level=logging.WARNING, format="%(levelname)s: %(message)s"
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        return _cmd_evaluate(args.event, args.rules)
    if args.command == "list-rules":
        return _cmd_list_rules()
    if args.command == "explain":
        return _cmd_explain(args.event)

    parser.print_help()
    return 0
