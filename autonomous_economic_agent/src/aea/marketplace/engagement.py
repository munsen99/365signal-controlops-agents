"""Bounded model-facing research, discovery, messaging, and outreach.

Research uses the pinned GET-only marketplace discovery client. Messaging is
possible only through an explicitly installed source-specific transport and
only for counterparties observed by this service instance. Follow-up state is
structured here; the supervisor may observe due conversations. The model does
not receive generic cron, web, email, or network tools.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from aea.marketplace.discovery import ALLOWED_ORIGINS
from aea.marketplace.intelligence import MarketObservation
from aea.marketplace.outbound import (
    OutboundAdapter,
    assess_publication_venues,
    build_outbound_offer,
)
from aea.marketplace.protocol import MarketplaceError
from aea.marketplace.sanitise import sanitise_marketplace_text
from aea.marketplace.scan import probe_markets, scan_observations
from aea.policy.reasons import HttpCode

MAX_MESSAGES_PER_HOUR = 3
MAX_TOTAL_MESSAGES_PER_HOUR = 10
DEFAULT_RESEARCH_MARKETS = ("the402", "moltjobs", "workpnp")
ALLOWED_CHANNELS = frozenset({"marketplace_api", "agent_protocol"})
LOCAL_PUBLICATION = "local"
HOSTILE_CONTENT = "HOSTILE_CONTENT"

_BINDING = re.compile(
    r"\b(i accept|we accept|deal agreed|contract agreed|final terms|i commit|"
    r"payment is guaranteed|send (?:the )?(?:payment|funds)|wallet address|"
    r"job confirmed|we have a contract|payment terms agreed)\b",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"\b(?:api[_ -]?key|private[_ -]?key|seed phrase|mnemonic|bearer|password|"
    r"AEA_(?:MODEL|CONTROL|SIGNER|WALLET|SUPERVISOR)_[A-Z_]+)\b",
    re.IGNORECASE,
)
_SUBCONTRACT_PAY = re.compile(
    r"\b(?:i(?:'ll| will) pay you|we will pay you|subcontract budget|"
    r"paid (?:sub)?contract|transfer (?:usdc|funds|sol)|fund escrow|"
    r"hire you for|paid delegation|i will spend)\b",
    re.IGNORECASE,
)
_URL_INJECTION = re.compile(
    r"(?:https?|file|ftp|ws|wss)://|\burl\s*=|\bGET\s+/|\bPOST\s+/",
    re.IGNORECASE,
)
_PUBLIC_COUNTERPARTY_ID = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")
_PUBLIC_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:@-]{1,200}$")
_PUBLIC_CONVERSATION_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class BoundedMessageTransport(Protocol):
    """One narrow adapter operation; no generic URL or method argument."""

    source: str

    def send_non_binding_message(
        self, *, counterparty_reference: str, intent: str, message: str, idempotency_key: str
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EngagementLimits:
    research_queries_per_hour: int = 10
    new_counterparties_per_hour: int = 10
    messages_per_counterparty_per_hour: int = MAX_MESSAGES_PER_HOUR
    total_messages_per_hour: int = MAX_TOTAL_MESSAGES_PER_HOUR
    new_counterparties_messaged_per_day: int = 10
    service_postings_per_day: int = 3
    max_followups_per_conversation: int = 3
    followup_cooldown_seconds: int = 3600
    conversation_ttl_seconds: int = 86400
    max_research_results: int = 10
    max_page_chars: int = 2000


def _default_research() -> dict[str, list[MarketObservation]]:
    # Three fixed origins at ten seconds each stay at the plugin's 30-second
    # request budget in the worst case. Live probes are typically sub-second.
    return probe_markets(markets=DEFAULT_RESEARCH_MARKETS)


def _confidence(row: MarketObservation) -> str:
    if row.funded is True and row.reward_usd is not None:
        return "0.900000"
    if row.external_id and row.reward_usd is not None:
        return "0.650000"
    return "0.350000"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _prune(bucket: deque[float], now: float, window: float) -> None:
    cutoff = now - window
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()


@dataclass
class _Conversation:
    conversation_id: str
    counterparty_id: str
    channel: str
    state: str
    last_message_at: float
    next_followup_after: float
    followup_count: int
    expires_at: float
    created_at: float
    messages: list[dict[str, Any]] = field(default_factory=list)


class EconomicEngagementService:
    def __init__(
        self,
        *,
        research_fn: Callable[..., dict[str, list[MarketObservation]]] = _default_research,
        transports: dict[str, BoundedMessageTransport] | None = None,
        now: Callable[[], float] = time.time,
        limits: EngagementLimits | None = None,
        publisher: OutboundAdapter | None = None,
    ) -> None:
        self._research_fn = research_fn
        self._transports = dict(transports or {})
        self._now = now
        self._limits = limits or EngagementLimits()
        self._publisher = publisher or OutboundAdapter()
        self._counterparties: dict[str, dict[str, Any]] = {}
        self._sent: dict[str, dict[str, Any]] = {}
        self._offers: dict[str, dict[str, Any]] = {}
        self._conversations: dict[str, _Conversation] = {}
        self._conversations_by_counterparty: dict[str, str] = {}
        self._per_counterparty: dict[str, deque[float]] = defaultdict(deque)
        self._all_sent: deque[float] = deque()
        self._research_times: deque[float] = deque()
        self._new_counterparties: deque[float] = deque()
        self._first_contact: dict[str, float] = {}
        self._offer_times: deque[float] = deque()
        self._last_boards: dict[str, list[MarketObservation]] = {}

    def _observations(self) -> list[MarketObservation]:
        boards = self._research_fn()
        if not isinstance(boards, dict):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed research result")
        rows: list[MarketObservation] = []
        for market, items in boards.items():
            if market not in ALLOWED_ORIGINS or not isinstance(items, list):
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed research result")
            if len(items) > 20:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "research result exceeded bound")
            for item in items:
                if not isinstance(item, MarketObservation):
                    raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed research observation")
                rows.append(item)
        self._last_boards = boards
        return rows

    def _rate_hour(self, bucket: deque[float], limit: int, *, message: str) -> None:
        now = self._now()
        _prune(bucket, now, 3600)
        if len(bucket) >= limit:
            raise MarketplaceError(HttpCode.FORBIDDEN, message)

    def _safe_query(self, query: str, *, label: str) -> Any:
        if _URL_INJECTION.search(query):
            raise MarketplaceError(HttpCode.FORBIDDEN, "arbitrary URL injection rejected")
        safe = sanitise_marketplace_text(query)
        if safe.prompt_injection:
            raise MarketplaceError(HttpCode.PROMPT_INJECTION_DETECTED, f"unsafe {label}")
        return safe

    def _guard_outbound_text(self, text: str, *, collaboration: bool = False) -> None:
        if _BINDING.search(text):
            raise MarketplaceError(HttpCode.POLICY_REJECTED, "binding or payment language rejected")
        if _SECRET.search(text):
            raise MarketplaceError(HttpCode.FORBIDDEN, "secret-like message content rejected")
        if collaboration and _SUBCONTRACT_PAY.search(text):
            raise MarketplaceError(HttpCode.FORBIDDEN, "paid subcontracting is prohibited")
        if sanitise_marketplace_text(text).prompt_injection:
            raise MarketplaceError(HttpCode.PROMPT_INJECTION_DETECTED, "unsafe message content")

    def _channels_for(self, source: str) -> list[str]:
        if source in self._transports:
            return ["marketplace_api"]
        return []

    def _transport(self, source: str) -> BoundedMessageTransport:
        transport = self._transports.get(source)
        if transport is None or transport.source != source:
            raise MarketplaceError(HttpCode.MARKETPLACE_UNAVAILABLE, "no bounded messaging endpoint configured")
        return transport

    def research_opportunities(self, *, query: str, limit: int) -> dict[str, Any]:
        # Query is classification context only. It is never interpolated into a
        # URL; providers and paths remain fixed in discovery.py.
        self._rate_hour(
            self._research_times,
            self._limits.research_queries_per_hour,
            message="research rate limit exceeded",
        )
        safe_query = self._safe_query(query, label="research query")
        cap = min(limit, self._limits.max_research_results)
        results: list[dict[str, Any]] = []
        for row in self._observations()[:cap]:
            title = sanitise_marketplace_text(row.title or "Untitled opportunity")
            summary = sanitise_marketplace_text(row.ineligibility_reason or row.status or "public listing")
            hostile = title.prompt_injection or summary.prompt_injection
            risk = [note for note in (row.ineligibility_reason,) if note]
            if hostile:
                risk.append(HOSTILE_CONTENT)
            results.append(
                {
                    "source": row.marketplace,
                    "title": title.wrapped,
                    "summary": _trim(summary.wrapped, self._limits.max_page_chars),
                    "url": ALLOWED_ORIGINS[row.marketplace],
                    "opportunity_type": row.category or "unknown",
                    "apparent_reward": None if row.reward_usd is None else str(row.reward_usd),
                    "settlement_asset": row.asset,
                    "settlement_chain": row.chain,
                    "counterparty": row.poster_id,
                    "requires_account": bool(row.authenticated_account_required),
                    "requires_wallet": bool(row.custody_or_vendor_wallet_required),
                    "requires_capital": row.funded is False,
                    "requires_hosting": bool(row.public_hosting_required),
                    "confidence": _confidence(row),
                    "risk_notes": risk,
                    "classification": HOSTILE_CONTENT if hostile else None,
                    "requires_followup": row.funded is not True or bool(row.vendor_clarification_required),
                    "untrusted": True,
                    "flags": sorted(set(title.flags + summary.flags)),
                }
            )
        self._research_times.append(self._now())
        return {"ok": True, "code": HttpCode.OK, "query": safe_query.preview, "results": results}

    def discover_counterparties(self, *, query: str, limit: int) -> dict[str, Any]:
        safe_query = self._safe_query(query, label="counterparty query")
        found: list[dict[str, Any]] = []
        now = self._now()
        for row in self._observations():
            if not row.poster_id or not _PUBLIC_COUNTERPARTY_ID.fullmatch(row.poster_id):
                continue
            if row.marketplace not in ALLOWED_ORIGINS:
                raise MarketplaceError(HttpCode.FORBIDDEN, "unknown source rejected")
            reference = f"{row.marketplace}:{row.poster_id}"
            existing = self._counterparties.get(reference)
            if existing is not None:
                existing["last_seen"] = now
                if len(found) < limit and all(item["counterparty_id"] != reference for item in found):
                    found.append(self._public_counterparty(existing))
                continue
            _prune(self._new_counterparties, now, 3600)
            if len(self._new_counterparties) >= self._limits.new_counterparties_per_hour:
                raise MarketplaceError(HttpCode.FORBIDDEN, "counterparty discovery rate limit exceeded")
            name = sanitise_marketplace_text(row.poster_id)
            demand = sanitise_marketplace_text(row.category or row.title or "unknown")
            channels = self._channels_for(row.marketplace)
            record = {
                "counterparty_id": reference,
                "source": row.marketplace,
                "endpoint_ref": row.poster_id,
                "public_identity": name.wrapped,
                "public_name": name.wrapped,
                "public_handle": row.poster_id,
                "agent_or_human": "unknown",
                "capabilities": [],
                "apparent_demand": demand.wrapped,
                "markets_seen": [row.marketplace],
                "supported_contact_channels": channels,
                "allowed_channels": channels,
                "settlement_preferences": [row.asset] if row.asset else [],
                "trust_state": "unverified",
                "trust_notes": ["public_unverified_identity"],
                "risk_notes": [
                    "public_unverified_identity",
                    *(row.ineligibility_reason and [row.ineligibility_reason] or []),
                ],
                "discovered_at": now,
                "last_seen": now,
                "message_count": 0,
                "conversation_state": "none",
                "untrusted": True,
            }
            self._counterparties[reference] = record
            self._new_counterparties.append(now)
            found.append(self._public_counterparty(record))
            if len(found) >= limit:
                break
        return {"ok": True, "code": HttpCode.OK, "query": safe_query.preview, "counterparties": found}

    def _public_counterparty(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "counterparty_id": record["counterparty_id"],
            "source": record["source"],
            "public_name": record["public_name"],
            "public_handle": record["public_handle"],
            "agent_or_human": record["agent_or_human"],
            "capabilities": list(record["capabilities"]),
            "apparent_demand": record["apparent_demand"],
            "markets_seen": list(record["markets_seen"]),
            "supported_contact_channels": list(record["supported_contact_channels"]),
            "public_contact_mechanism": (
                record["supported_contact_channels"][0]
                if record["supported_contact_channels"]
                else "none_supported"
            ),
            "settlement_preferences": list(record["settlement_preferences"]),
            "trust_notes": list(record["trust_notes"]),
            "risk_notes": list(record["risk_notes"]),
            "last_seen": _iso(float(record["last_seen"])),
            "untrusted": True,
        }

    def get_counterparty_profile(self, *, counterparty_id: str) -> dict[str, Any]:
        known = self._counterparties.get(counterparty_id)
        if known is None:
            raise MarketplaceError(HttpCode.NOT_FOUND, "counterparty was not discovered")
        public = self._public_counterparty(known)
        public.update(
            {
                "endpoint_ref": known["endpoint_ref"],
                "trust_state": known["trust_state"],
                "allowed_channels": list(known["allowed_channels"]),
                "message_count": known["message_count"],
                "conversation_state": known["conversation_state"],
                "discovered_at": _iso(float(known["discovered_at"])),
            }
        )
        return {"ok": True, "code": HttpCode.OK, "counterparty": public}

    def get_market_status(self, *, marketplace: str | None = None) -> dict[str, Any]:
        if marketplace is not None and marketplace not in ALLOWED_ORIGINS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "unknown source rejected")
        rows = self._observations()
        boards = self._last_boards
        if marketplace is not None:
            boards = {marketplace: boards.get(marketplace, [])}
            rows = [row for row in rows if row.marketplace == marketplace]
        scan = scan_observations(boards)
        markets = []
        for name, items in boards.items():
            markets.append(
                {
                    "marketplace": name,
                    "origin": ALLOWED_ORIGINS[name],
                    "listings": len(items),
                    "read_only": True,
                }
            )
        return {
            "ok": True,
            "code": HttpCode.OK,
            "markets": markets,
            "listing_count": len(rows),
            "eligible_count": scan["eligible_count"],
            "classification_counts": scan["classification_counts"],
            "capital_bearing_actions": [],
            "wallet_authority_expansion": False,
            "paid_subcontracting": False,
            "live_revenue_mission": False,
            "untrusted": True,
        }

    def send_message(
        self,
        *,
        counterparty_id: str,
        intent: str,
        message: str,
        idempotency_key: str,
        channel: str = "marketplace_api",
    ) -> dict[str, Any]:
        prior = self._sent.get(idempotency_key)
        if prior is not None:
            return {**prior, "code": HttpCode.IDEMPOTENT_REPLAY, "replay": True}
        return self._deliver(
            counterparty_id=counterparty_id,
            channel=channel,
            intent=intent,
            message=message,
            idempotency_key=idempotency_key,
        )

    def propose_collaboration(
        self,
        *,
        counterparty_id: str,
        proposal: str,
        idempotency_key: str,
        channel: str = "marketplace_api",
    ) -> dict[str, Any]:
        prior = self._sent.get(idempotency_key)
        if prior is not None:
            return {**prior, "code": HttpCode.IDEMPOTENT_REPLAY, "replay": True}
        result = self._deliver(
            counterparty_id=counterparty_id,
            channel=channel,
            intent="propose_non_binding_collaboration",
            message=proposal,
            idempotency_key=idempotency_key,
            collaboration=True,
        )
        result["paid_subcontracting"] = False
        result["financial_obligation"] = False
        return result

    def _deliver(
        self,
        *,
        counterparty_id: str,
        channel: str,
        intent: str,
        message: str,
        idempotency_key: str,
        collaboration: bool = False,
        follow_up: bool = False,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        known = self._counterparties.get(counterparty_id)
        if known is None:
            raise MarketplaceError(HttpCode.FORBIDDEN, "counterparty was not discovered")
        if channel not in ALLOWED_CHANNELS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "channel is not an approved economic channel")
        known["allowed_channels"] = self._channels_for(str(known["source"]))
        known["supported_contact_channels"] = list(known["allowed_channels"])
        if channel not in known["allowed_channels"]:
            raise MarketplaceError(HttpCode.FORBIDDEN, "channel is not allowed for this counterparty")
        self._guard_outbound_text(message, collaboration=collaboration)
        source = str(known["source"])
        transport = self._transport(source)
        now = self._now()
        _prune(self._per_counterparty[counterparty_id], now, 3600)
        _prune(self._all_sent, now, 3600)
        if (
            len(self._per_counterparty[counterparty_id]) >= self._limits.messages_per_counterparty_per_hour
            or len(self._all_sent) >= self._limits.total_messages_per_hour
        ):
            raise MarketplaceError(HttpCode.FORBIDDEN, "message rate limit exceeded")
        first_contacts = [
            ts for ts in self._first_contact.values() if ts > now - 86400
        ]
        if counterparty_id not in self._first_contact and len(first_contacts) >= self._limits.new_counterparties_messaged_per_day:
            raise MarketplaceError(HttpCode.FORBIDDEN, "new counterparty messaging rate limit exceeded")
        identified = f"Econo (automated economic agent): {message.strip()}"
        result = transport.send_non_binding_message(
            counterparty_reference=str(known["endpoint_ref"]),
            intent=intent,
            message=identified,
            idempotency_key=idempotency_key,
        )
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(message_id, str) or not _PUBLIC_MESSAGE_ID.fullmatch(message_id):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed messaging response")
        self._per_counterparty[counterparty_id].append(now)
        self._all_sent.append(now)
        self._first_contact.setdefault(counterparty_id, now)
        known["message_count"] = int(known["message_count"]) + 1
        known["last_seen"] = now
        conversation = self._touch_conversation(
            counterparty_id=counterparty_id,
            channel=channel,
            now=now,
            conversation_id=conversation_id,
            follow_up=follow_up,
        )
        conversation.messages.append(
            {
                "message_id": message_id,
                "direction": "out",
                "intent": intent,
                "body": identified,
                "created_at": now,
                "untrusted": False,
            }
        )
        output = {
            "ok": True,
            "code": HttpCode.OK,
            "message_id": message_id,
            "conversation_id": conversation.conversation_id,
            "counterparty_id": counterparty_id,
            "channel": channel,
            "intent": intent,
            "non_binding": True,
            "automated_agent_disclosed": True,
            "replay": False,
        }
        self._sent[idempotency_key] = output
        return dict(output)

    def _touch_conversation(
        self,
        *,
        counterparty_id: str,
        channel: str,
        now: float,
        conversation_id: str | None,
        follow_up: bool,
    ) -> _Conversation:
        if conversation_id is not None:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.counterparty_id != counterparty_id:
                raise MarketplaceError(HttpCode.NOT_FOUND, "conversation was not found")
        else:
            existing_id = self._conversations_by_counterparty.get(counterparty_id)
            conversation = self._conversations.get(existing_id) if existing_id else None
        if conversation is None or now >= conversation.expires_at:
            conversation = _Conversation(
                conversation_id=str(uuid4()),
                counterparty_id=counterparty_id,
                channel=channel,
                state="awaiting_response",
                last_message_at=now,
                next_followup_after=now + self._limits.followup_cooldown_seconds,
                followup_count=0,
                expires_at=now + self._limits.conversation_ttl_seconds,
                created_at=now,
            )
            self._conversations[conversation.conversation_id] = conversation
            self._conversations_by_counterparty[counterparty_id] = conversation.conversation_id
        conversation.last_message_at = now
        conversation.state = "awaiting_response"
        conversation.channel = channel
        if follow_up:
            conversation.followup_count += 1
            conversation.next_followup_after = now + self._limits.followup_cooldown_seconds
        self._counterparties[counterparty_id]["conversation_state"] = conversation.state
        return conversation

    def read_messages(
        self,
        *,
        counterparty_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        conversation = self._resolve_conversation(counterparty_id, conversation_id)
        known = self._counterparties[conversation.counterparty_id]
        transport = self._transports.get(str(known["source"]))
        reader = getattr(transport, "read_inbound_messages", None) if transport is not None else None
        if callable(reader):
            inbound = reader(counterparty_reference=str(known["endpoint_ref"]))
            if not isinstance(inbound, list):
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed messaging response")
            for item in inbound:
                self._ingest_inbound(conversation, item)
        messages = []
        for item in conversation.messages[-limit:]:
            body = sanitise_marketplace_text(str(item.get("body") or ""))
            hostile = body.prompt_injection or bool(_SECRET.search(body.original))
            messages.append(
                {
                    "message_id": item["message_id"],
                    "direction": item["direction"],
                    "intent": item.get("intent"),
                    "body": body.wrapped,
                    "created_at": _iso(float(item["created_at"])),
                    "untrusted": item.get("direction") == "in",
                    "classification": HOSTILE_CONTENT if hostile else None,
                    "flags": list(body.flags),
                }
            )
        return {
            "ok": True,
            "code": HttpCode.OK,
            "conversation_id": conversation.conversation_id,
            "counterparty_id": conversation.counterparty_id,
            "messages": messages,
        }

    def _ingest_inbound(self, conversation: _Conversation, item: object) -> None:
        if not isinstance(item, dict):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed messaging response")
        message_id = item.get("message_id")
        body = item.get("body") or item.get("message")
        if not isinstance(message_id, str) or not _PUBLIC_MESSAGE_ID.fullmatch(message_id):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed messaging response")
        if not isinstance(body, str):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed messaging response")
        if any(existing["message_id"] == message_id for existing in conversation.messages):
            return
        conversation.messages.append(
            {
                "message_id": message_id,
                "direction": "in",
                "intent": item.get("intent"),
                "body": body,
                "created_at": self._now(),
                "untrusted": True,
            }
        )
        conversation.state = "active"
        self._counterparties[conversation.counterparty_id]["conversation_state"] = "active"

    def _resolve_conversation(
        self, counterparty_id: str | None, conversation_id: str | None
    ) -> _Conversation:
        if conversation_id:
            if not _PUBLIC_CONVERSATION_ID.fullmatch(conversation_id):
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed conversation id")
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise MarketplaceError(HttpCode.NOT_FOUND, "conversation was not found")
            if counterparty_id and conversation.counterparty_id != counterparty_id:
                raise MarketplaceError(HttpCode.FORBIDDEN, "conversation does not match counterparty")
            return conversation
        if not counterparty_id:
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "counterparty_id or conversation_id is required")
        if counterparty_id not in self._counterparties:
            raise MarketplaceError(HttpCode.FORBIDDEN, "counterparty was not discovered")
        existing_id = self._conversations_by_counterparty.get(counterparty_id)
        conversation = self._conversations.get(existing_id) if existing_id else None
        if conversation is None:
            raise MarketplaceError(HttpCode.NOT_FOUND, "conversation was not found")
        return conversation

    def follow_up_message(
        self,
        *,
        conversation_id: str,
        message: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        prior = self._sent.get(idempotency_key)
        if prior is not None:
            return {**prior, "code": HttpCode.IDEMPOTENT_REPLAY, "replay": True}
        conversation = self._resolve_conversation(None, conversation_id)
        now = self._now()
        if now >= conversation.expires_at:
            conversation.state = "expired"
            self._counterparties[conversation.counterparty_id]["conversation_state"] = "expired"
            raise MarketplaceError(HttpCode.FORBIDDEN, "conversation has expired")
        if conversation.followup_count >= self._limits.max_followups_per_conversation:
            raise MarketplaceError(HttpCode.FORBIDDEN, "follow-up rate limit exceeded")
        if now < conversation.next_followup_after:
            raise MarketplaceError(HttpCode.FORBIDDEN, "follow-up cooldown active")
        result = self._deliver(
            counterparty_id=conversation.counterparty_id,
            channel=conversation.channel,
            intent="follow_up",
            message=message,
            idempotency_key=idempotency_key,
            follow_up=True,
            conversation_id=conversation.conversation_id,
        )
        result["followup_count"] = conversation.followup_count
        result["next_followup_after"] = _iso(conversation.next_followup_after)
        return result

    def list_active_conversations(self, *, limit: int = 10) -> dict[str, Any]:
        now = self._now()
        active: list[dict[str, Any]] = []
        for conversation in self._conversations.values():
            if now >= conversation.expires_at:
                conversation.state = "expired"
                known = self._counterparties.get(conversation.counterparty_id)
                if known is not None:
                    known["conversation_state"] = "expired"
                continue
            due = now >= conversation.next_followup_after and conversation.state == "awaiting_response"
            active.append(
                {
                    "conversation_id": conversation.conversation_id,
                    "counterparty_id": conversation.counterparty_id,
                    "channel": conversation.channel,
                    "state": conversation.state,
                    "last_message_at": _iso(conversation.last_message_at),
                    "next_followup_after": _iso(conversation.next_followup_after),
                    "followup_count": conversation.followup_count,
                    "expires_at": _iso(conversation.expires_at),
                    "followup_due": due,
                }
            )
            if len(active) >= limit:
                break
        return {"ok": True, "code": HttpCode.OK, "conversations": active}

    def due_followups(self) -> list[dict[str, Any]]:
        """Supervisor-facing read of conversations whose follow-up is due."""
        listed = self.list_active_conversations(limit=50)
        return [row for row in listed["conversations"] if row.get("followup_due")]

    def post_service_offer(
        self,
        *,
        marketplace: str = LOCAL_PUBLICATION,
        service_id: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        prior = self._offers.get(idempotency_key)
        if prior is not None:
            return {**prior, "code": HttpCode.IDEMPOTENT_REPLAY, "replay": True}
        now = self._now()
        _prune(self._offer_times, now, 86400)
        if len(self._offer_times) >= self._limits.service_postings_per_day:
            raise MarketplaceError(HttpCode.FORBIDDEN, "service posting rate limit exceeded")
        if marketplace != LOCAL_PUBLICATION:
            known_venues = {item.marketplace: item for item in assess_publication_venues()}
            if marketplace not in known_venues and marketplace not in ALLOWED_ORIGINS:
                raise MarketplaceError(HttpCode.FORBIDDEN, "unknown source rejected")
            venue = known_venues.get(marketplace)
            if venue is None or not venue.compatible:
                blocked = venue.required_blocked_action if venue is not None else "unsupported"
                if blocked in {
                    "account_creation_secret_and_identity_claim",
                    "operator_credentials",
                    "vendor_custody",
                    "wallet_signing",
                    "private_key_generation",
                }:
                    raise MarketplaceError(
                        HttpCode.POLICY_REJECTED,
                        "fee/capital or credential requirement rejected",
                    )
                raise MarketplaceError(HttpCode.FORBIDDEN, "unsupported marketplace rejected")
        offer = build_outbound_offer()
        if service_id is not None:
            services = [item for item in offer.services if item.id == service_id]
            if not services:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "unknown service_id")
            offer = offer.model_copy(update={"services": services})
        advertised = self._publisher.advertise(offer)
        payload = advertised.model_dump(mode="json")
        output = {
            "ok": True,
            "code": HttpCode.OK,
            "offer_id": advertised.advertisement_id or f"local-offer-{uuid4()}",
            "published": advertised.published,
            "marketplace": advertised.marketplace or LOCAL_PUBLICATION,
            "mode": advertised.mode,
            "reason": advertised.reason,
            "canonical_profile": True,
            "non_binding": True,
            "paid_promotion": False,
            "listing_fee": False,
            "escrow_funded": False,
            "wallet_authority": False,
            "services": payload.get("payload", {}).get("canonical", {}).get("services", []),
            "public_text": payload.get("payload", {}).get("public_text"),
            "replay": False,
        }
        self._offer_times.append(now)
        self._offers[idempotency_key] = output
        return dict(output)
