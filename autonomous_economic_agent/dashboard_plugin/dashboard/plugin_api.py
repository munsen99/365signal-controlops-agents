"""Read-only AEA dashboard plugin API.

Mounted at /api/plugins/aea/ by the Hermes dashboard. The browser talks only
to this plugin; this process GETs the AEA control observability endpoint.

No sign, send, approve, enable, unfreeze, debit, or policy mutation routes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

CONTROL_DEFAULT = "http://127.0.0.1:18700"
OBSERVABILITY_PATH = "/observability/status"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
REQUEST_TIMEOUT_SECONDS = 3.0
FORBIDDEN_PATH_PARTS = (
    "/v1/sign",
    "/v1/wallet/debit",
    "/v1/admin/",
    "/v1/execute-payment",
    "/v1/payment-requests",
    "/v1/tools/",
)


def _read_token() -> str:
    value = os.environ.get("AEA_OBSERVABILITY_TOKEN", "")
    if value:
        return value
    path = os.environ.get("AEA_OBSERVABILITY_TOKEN_FILE")
    if not path:
        candidate = Path("/opt/data/aea/observability.token")
        if candidate.is_file():
            path = str(candidate)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return ""


def _control_url() -> str:
    raw = os.environ.get("AEA_CONTROL_URL", CONTROL_DEFAULT).strip() or CONTROL_DEFAULT
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError("AEA_CONTROL_URL must be loopback HTTP")
    if parsed.username or parsed.password:
        raise ValueError("AEA_CONTROL_URL must not contain credentials")
    return raw.rstrip("/")


def _assert_read_only_target(url: str) -> None:
    parsed = urlparse(url)
    path = parsed.path or ""
    if path != OBSERVABILITY_PATH:
        raise ValueError("dashboard may only GET /observability/status")
    lowered = url.lower()
    if any(part in lowered for part in FORBIDDEN_PATH_PARTS):
        raise ValueError("dashboard cannot call signer, debit, admin, or tools routes")


def fetch_observability_status() -> tuple[int, dict[str, Any]]:
    """GET the AEA observability snapshot. Never POST. Never call the signer."""
    token = _read_token()
    if not token:
        return 503, {
            "ok": False,
            "code": "UNAUTHENTICATED",
            "agent": {"state": "offline", "health": "unavailable"},
            "detail": "observability token is not configured on the dashboard host",
        }
    try:
        base = _control_url()
    except ValueError as exc:
        return 503, {
            "ok": False,
            "code": "NETWORK_FAILURE",
            "agent": {"state": "offline", "health": "unavailable"},
            "detail": str(exc),
        }
    url = base + OBSERVABILITY_PATH
    _assert_read_only_target(url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            status_code = int(response.status)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            body = json.loads(raw) if raw else {"ok": False, "code": "UNAUTHENTICATED"}
        except json.JSONDecodeError:
            body = {"ok": False, "code": "NETWORK_FAILURE"}
        if not isinstance(body, dict):
            body = {"ok": False, "code": "NETWORK_FAILURE"}
        body.setdefault("agent", {"state": "offline", "health": "unavailable"})
        return int(exc.code), body
    except TimeoutError:
        return 504, {
            "ok": False,
            "code": "TIMEOUT",
            "agent": {"state": "offline", "health": "unavailable"},
            "detail": "AEA observability request timed out",
        }
    except URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        code = "TIMEOUT" if "timed out" in reason.lower() else "NETWORK_FAILURE"
        http_status = 504 if code == "TIMEOUT" else 503
        return http_status, {
            "ok": False,
            "code": code,
            "agent": {"state": "offline", "health": "unavailable"},
            "detail": "AEA observability endpoint unavailable",
        }
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return 502, {
            "ok": False,
            "code": "INTERNAL_ERROR",
            "agent": {"state": "offline", "health": "unavailable"},
        }
    if not isinstance(body, dict):
        return 502, {
            "ok": False,
            "code": "INTERNAL_ERROR",
            "agent": {"state": "offline", "health": "unavailable"},
        }
    return status_code, body


@router.get("/status")
def get_status() -> JSONResponse:
    status_code, body = fetch_observability_status()
    return JSONResponse(content=body, status_code=status_code)
