"""Deterministic M1 Gate A driver.

This is deliberately only a caller of the shared model-scoped ToolClient.  It
has no service objects, control credentials, or test-only mutation methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aea.tools_client.http import ToolClient


@dataclass
class GateARun:
    calls: list[dict[str, Any]] = field(default_factory=list)
    starting_state: dict[str, Any] = field(default_factory=dict)
    final_state: dict[str, Any] = field(default_factory=dict)
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    completed: dict[str, Any] = field(default_factory=dict)


class GateADriver:
    """A Hermes-plugin-equivalent deterministic nine-tool client."""

    def __init__(self, client: ToolClient, *, run_id: str) -> None:
        self.client = client
        self.run_id = run_id
        self.result = GateARun()

    def _call(self, name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = body or {}
        result = self.client.call(
            name,
            payload,
            correlation_id=f"00000000-0000-4000-8000-{len(self.result.calls) + 1:012d}",
        )
        # Evidence contains contracts and identifiers, never headers or credentials.
        self.result.calls.append({"tool": name, "request": payload, "result": result})
        return result

    def run(self) -> GateARun:
        self.result.starting_state = self._call("get_financial_state")
        discovered = self._call("find_jobs", {"limit": 20})
        selected: tuple[dict[str, Any], dict[str, Any]] | None = None
        for index, job in enumerate(discovered["jobs"]):
            evaluation = self._call(
                "evaluate_job",
                {
                    "opportunity_id": job["opportunity_id"],
                    "idempotency_key": f"gate-a-eval-{index:02d}",
                },
            )
            self.result.evaluations.append(evaluation)
            decision = self._call(
                "record_decision",
                {
                    "opportunity_id": job["opportunity_id"],
                    "decision_type": "evaluate",
                    "decision": "accept" if evaluation.get("recommendation") == "accept" else "decline",
                    "reasoning_summary": str(
                        evaluation.get("reason_code") or evaluation.get("recommendation")
                    ),
                    "idempotency_key": f"gate-a-decision-{index:02d}",
                },
            )
            self.result.decisions.append(decision)
            if selected is None and evaluation.get("recommendation") == "accept":
                selected = (job, evaluation)
        if selected is None:
            raise AssertionError("fixture catalogue contains no policy-and-risk permitted profitable job")
        job, evaluation = selected
        accepted = self._call(
            "accept_job",
            {"opportunity_id": job["opportunity_id"], "idempotency_key": "gate-a-accept-01"},
        )
        job_id = accepted["job_id"]
        performed = self._call(
            "perform_job", {"job_id": job_id, "idempotency_key": "gate-a-perform-01"}
        )
        submitted = self._call(
            "submit_work", {"job_id": job_id, "idempotency_key": "gate-a-submit-01"}
        )
        payment = self._call(
            "check_payment", {"job_id": job_id, "idempotency_key": "gate-a-check-01"}
        )
        self.result.final_state = self._call("get_financial_state")
        self.result.completed = {
            "external_reference": job["external_reference"],
            "evaluation": evaluation,
            "accept": accepted,
            "perform": performed,
            "submit": submitted,
            "payment": payment,
        }
        return self.result
