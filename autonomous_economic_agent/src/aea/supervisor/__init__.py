"""Independent supervisor. Freeze, signer disable, and loop stop.

Not part of the LLM planning loop. Holds no debit, credit, HMAC, or
signer-approval authority. Mutations require AEA_SUPERVISOR_TOKEN.
"""

from aea.supervisor.monitors import MonitorDecision, MonitorSnapshot, evaluate_monitors
from aea.supervisor.service import SUPERVISOR_HOST, SUPERVISOR_PORT, create_app

__all__ = [
    "SUPERVISOR_HOST",
    "SUPERVISOR_PORT",
    "MonitorDecision",
    "MonitorSnapshot",
    "create_app",
    "evaluate_monitors",
]
