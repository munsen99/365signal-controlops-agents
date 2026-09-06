"""Bounded source-specific outbound transport: probe then source-level refusal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aea.marketplace.protocol import MarketplaceError
from aea.marketplace.transport import BoundedSourceTransport, SOURCE_REFUSALS, default_bounded_transports
from aea.policy.reasons import HttpCode


class FakeClient:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append((method, str(url)))
        assert method == "GET"
        assert kwargs.get("follow_redirects") is False
        return SimpleNamespace(status_code=self.status, headers={})


def test_default_transports_cover_allowlisted_sources_only() -> None:
    client = FakeClient()
    transports = default_bounded_transports(client=client)
    assert set(transports) == {"the402", "moltjobs", "workpnp", "hober", "bothire"}


def test_message_transport_probes_then_refuses_with_source_reason() -> None:
    client = FakeClient(status=200)
    transport = BoundedSourceTransport("workpnp", client=client)
    with pytest.raises(MarketplaceError) as exc:
        transport.send_non_binding_message(
            counterparty_reference="job_412n2v0mvb13s0jr",
            intent="ask_work_available",
            message="Is legitimate bounded research work currently available?",
            idempotency_key="msg-workpnp-0001",
        )
    assert exc.value.code == HttpCode.POLICY_REJECTED
    assert "workpnp" in exc.value.message
    assert "POST /agents/register" in exc.value.message
    assert "HTTP 200" in exc.value.message
    assert client.calls == [("GET", "https://workpnp.com/api/v1/jobs")]
    assert "bid" in SOURCE_REFUSALS["workpnp"]


def test_transport_does_not_post_or_bid() -> None:
    src = __import__("inspect").getsource(BoundedSourceTransport.send_non_binding_message)
    assert "POST" not in src
    assert "bid" not in src.lower()
    client_src = __import__("inspect").getsource(BoundedSourceTransport._probe)
    assert '"GET"' in client_src or "'GET'" in client_src
