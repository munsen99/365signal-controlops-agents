"""Pure public-source candidate policy. A decision never authorises a connection."""

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_network
import re
from types import MappingProxyType

from . import policy_data as _data

__all__ = ["Decision", "ReasonCode", "UrlDecision", "evaluate_url"]


class Decision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class ReasonCode(StrEnum):
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"
    FORBIDDEN_RAW_CHARACTER = "FORBIDDEN_RAW_CHARACTER"
    MALFORMED_PERCENT_ESCAPE = "MALFORMED_PERCENT_ESCAPE"
    FORBIDDEN_ENCODED_CHARACTER = "FORBIDDEN_ENCODED_CHARACTER"
    MALFORMED_URL = "MALFORMED_URL"
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
    USERINFO_FORBIDDEN = "USERINFO_FORBIDDEN"
    ENCODED_AUTHORITY_FORBIDDEN = "ENCODED_AUTHORITY_FORBIDDEN"
    INVALID_PORT = "INVALID_PORT"
    PORT_NOT_PERMITTED = "PORT_NOT_PERMITTED"
    HOST_NOT_PERMITTED = "HOST_NOT_PERMITTED"
    DESTINATION_PROHIBITED = "DESTINATION_PROHIBITED"
    INVALID_COMPONENT = "INVALID_COMPONENT"
    DOT_SEGMENT_FORBIDDEN = "DOT_SEGMENT_FORBIDDEN"
    HTTP_NOT_PERMITTED = "HTTP_NOT_PERMITTED"
    PUBLIC_URL_CANDIDATE = "PUBLIC_URL_CANDIDATE"


@dataclass(frozen=True, slots=True)
class UrlDecision:
    original_url: str | None = field(repr=False)
    decision: Decision
    reason_code: ReasonCode
    policy_version: str | None
    canonical_url: str | None
    host: str | None
    host_kind: str | None
    effective_port: int | None
    explanation: str
    requested_human_action: str | None

    def __bool__(self) -> bool:
        raise TypeError("Compare the explicit decision; UrlDecision has no truth value")


_VERSION = "controlops-public-url/v1.0.0"
# Pins the reviewed version and table contents independently of policy_data.
_DATA_FINGERPRINT = "060014a20a59ed192987bb6fa55f321b9e5e9abef162597dd26d9540b7f718db"
_DATA_FIELDS = ("IPV4_DENY", "IPV6_ELIGIBILITY", "IPV6_DENY", "NAMESPACE_DENY")
_MESSAGES = MappingProxyType({
    ReasonCode.POLICY_UNAVAILABLE: "The required policy data is unavailable or invalid.",
    ReasonCode.INVALID_INPUT: "A nonempty built-in string is required.",
    ReasonCode.FORBIDDEN_RAW_CHARACTER: "The URL contains a forbidden raw character.",
    ReasonCode.MALFORMED_PERCENT_ESCAPE: "The URL contains a malformed percent escape.",
    ReasonCode.FORBIDDEN_ENCODED_CHARACTER: "The URL encodes a forbidden control or backslash character.",
    ReasonCode.MALFORMED_URL: "The URL does not have an unambiguous absolute authority structure.",
    ReasonCode.UNSUPPORTED_SCHEME: "The URL scheme is not supported by this policy.",
    ReasonCode.USERINFO_FORBIDDEN: "URL userinfo is forbidden.",
    ReasonCode.ENCODED_AUTHORITY_FORBIDDEN: "Percent encoding in the URL authority is forbidden.",
    ReasonCode.INVALID_PORT: "The explicit port is invalid or noncanonical.",
    ReasonCode.PORT_NOT_PERMITTED: "The explicit port is not permitted.",
    ReasonCode.HOST_NOT_PERMITTED: "The host representation does not satisfy the policy.",
    ReasonCode.DESTINATION_PROHIBITED: "The destination is excluded by the address or namespace policy.",
    ReasonCode.INVALID_COMPONENT: "A URL component contains an invalid character.",
    ReasonCode.DOT_SEGMENT_FORBIDDEN: "The URL path contains a prohibited dot segment.",
    ReasonCode.HTTP_NOT_PERMITTED: "HTTP requires human assessment and cannot proceed automatically.",
    ReasonCode.PUBLIC_URL_CANDIDATE: "Candidate source accepted by deterministic URL policy.",
})
_REVIEW_ACTION = (
    "Supply a compliant replacement URL, abandon this source, or propose a future governed policy change."
)
_URL = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)([^?#]*)(?:\?([^#]*))?(?:#(.*))?")
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_PORT = re.compile(r"[1-9][0-9]{0,4}")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_PCHAR = r"(?:[A-Za-z0-9._~!$&'()*+,;=:@]|%[0-9A-Fa-f]{2})"
_PATH = re.compile(r"(?:" + _PCHAR + r"|/)*")
_QUERY_FRAGMENT = re.compile(r"(?:" + _PCHAR + r"|[/?])*")
_DOT_ESCAPE = re.compile(r"%2e", re.IGNORECASE)


def _load_policy():
    """Validate only compiled local data. Never consult files or host settings."""
    version = getattr(_data, "POLICY_VERSION", None)
    tables = tuple(getattr(_data, name, None) for name in _DATA_FIELDS)
    if type(version) is not str or version != _VERSION:
        return None
    if any(type(table) is not tuple or not table or
           any(type(item) is not str for item in table) for table in tables):
        return None
    parts = [version]
    for name, table in zip(_DATA_FIELDS, tables):
        parts.extend((name, *table))
    try:
        if sha256("\n".join(parts).encode("ascii")).hexdigest() != _DATA_FINGERPRINT:
            return None
        networks = tuple(tuple(ip_network(cidr, strict=True) for cidr in table)
                         for table in tables[:3])
    except (ValueError, UnicodeError):
        return None
    if any(net.version != family for table, family in zip(networks, (4, 6, 6))
           for net in table):
        return None
    return (*networks, tables[3])


def _reject(value: object, reason: ReasonCode) -> UrlDecision:
    return UrlDecision(
        original_url=value if type(value) is str else None,
        decision=Decision.REJECT, reason_code=reason,
        policy_version=None if reason is ReasonCode.POLICY_UNAVAILABLE else _VERSION,
        canonical_url=None, host=None, host_kind=None, effective_port=None,
        explanation=_MESSAGES[reason], requested_human_action=None,
    )


def _authority(authority: str):
    """Separate host/port structurally, without interpreting credentials or ports."""
    destination = authority.rsplit("@", 1)[-1]
    if not destination:
        return None
    if destination.startswith("["):
        if destination.count("[") != 1 or destination.count("]") != 1:
            return None
        host, _, tail = destination[1:].partition("]")
        if not host or (tail and not tail.startswith(":")):
            return None
        return host, tail[1:] if tail else None, True
    if "[" in destination or "]" in destination or destination.count(":") > 1:
        return None
    host, separator, port = destination.partition(":")
    if not host:
        return None
    return host, port if separator else None, False


def _canonical_ipv6(address: IPv6Address) -> str:
    # Explicit hex-only rendering avoids Python-version changes to mapped IPv6
    # str()/compressed (which can render a dotted IPv4 tail).
    groups = [format((int(address) >> shift) & 65535, "x")
              for shift in range(112, -1, -16)]
    best_start, best_length = 0, 0
    index = 0
    while index < 8:
        end = index
        while end < 8 and groups[end] == "0":
            end += 1
        length = end - index
        if length > best_length:
            best_start, best_length = index, length
        index = max(index + 1, end)
    if best_length < 2:
        return ":".join(groups)
    return (":".join(groups[:best_start]) + "::" +
            ":".join(groups[best_start + best_length:]))


def _host(raw: str, bracketed: bool):
    """Return canonical host, kind and optional numeric address, or None."""
    if bracketed:
        if "." in raw or "%" in raw:
            return None
        try:
            address = IPv6Address(raw)
        except ValueError:
            return None
        if raw != _canonical_ipv6(address):
            return None
        return raw, "ipv6", address
    if re.fullmatch(r"[0-9.]+", raw):
        octets = raw.split(".")
        if len(octets) != 4 or any(
            not re.fullmatch(r"0|[1-9][0-9]{0,2}", x) or int(x) > 255 for x in octets
        ):
            return None
        return raw, "ipv4", IPv4Address(raw)
    host = raw.lower()
    labels = host.split(".")
    if (len(host) > 253 or len(labels) < 2 or
            not re.fullmatch(r"[a-z]{2,}", labels[-1]) or
            any(not _LABEL.fullmatch(label) or label.startswith("xn--") for label in labels)):
        return None
    return host, "dns", None


def evaluate_url(value: object) -> UrlDecision:
    """Classify a candidate without I/O; only an exact built-in str is accepted."""
    policy = _load_policy()
    if policy is None:
        return _reject(value, ReasonCode.POLICY_UNAVAILABLE)
    if type(value) is not str or not value:
        return _reject(value, ReasonCode.INVALID_INPUT)
    if any(ord(char) <= 32 or ord(char) >= 127 or char == "\\" for char in value):
        return _reject(value, ReasonCode.FORBIDDEN_RAW_CHARACTER)
    if _BAD_ESCAPE.search(value):
        return _reject(value, ReasonCode.MALFORMED_PERCENT_ESCAPE)
    if any(int(match[0][1:], 16) < 32 or int(match[0][1:], 16) in (92, 127)
           for match in _ESCAPE.finditer(value)):
        return _reject(value, ReasonCode.FORBIDDEN_ENCODED_CHARACTER)
    match = _URL.fullmatch(value)
    if match is None:
        return _reject(value, ReasonCode.MALFORMED_URL)
    scheme, authority, path, query, fragment = match.groups()
    destination = _authority(authority)
    if destination is None:
        return _reject(value, ReasonCode.MALFORMED_URL)
    scheme = scheme.lower()
    if scheme not in ("http", "https"):
        return _reject(value, ReasonCode.UNSUPPORTED_SCHEME)
    if "@" in authority:
        return _reject(value, ReasonCode.USERINFO_FORBIDDEN)
    if "%" in authority:
        return _reject(value, ReasonCode.ENCODED_AUTHORITY_FORBIDDEN)
    raw_host, port, bracketed = destination
    if port is not None:
        if not _PORT.fullmatch(port) or int(port) > 65535:
            return _reject(value, ReasonCode.INVALID_PORT)
        if port != "443":
            return _reject(value, ReasonCode.PORT_NOT_PERMITTED)
    parsed_host = _host(raw_host, bracketed)
    if parsed_host is None:
        return _reject(value, ReasonCode.HOST_NOT_PERMITTED)
    host, kind, address = parsed_host
    deny4, allow6, deny6, namespaces = policy
    if kind == "dns":
        prohibited = any(host == suffix or host.endswith("." + suffix) for suffix in namespaces)
    elif kind == "ipv4":
        prohibited = any(address in net for net in deny4)
    else:
        prohibited = (not any(address in net for net in allow6) or
                      any(address in net for net in deny6))
    if prohibited:
        return _reject(value, ReasonCode.DESTINATION_PROHIBITED)
    if (not _PATH.fullmatch(path) or
            (query is not None and not _QUERY_FRAGMENT.fullmatch(query)) or
            (fragment is not None and not _QUERY_FRAGMENT.fullmatch(fragment))):
        return _reject(value, ReasonCode.INVALID_COMPONENT)
    if any(_DOT_ESCAPE.sub(".", segment) in (".", "..") for segment in path.split("/")):
        return _reject(value, ReasonCode.DOT_SEGMENT_FORBIDDEN)
    canonical = scheme + "://" + ("[" + host + "]" if bracketed else host)
    if scheme == "http" and port is not None:
        canonical += ":443"
    canonical += path or "/"
    if query is not None:
        canonical += "?" + query
    canonical = _ESCAPE.sub(lambda escaped: escaped[0].upper(), canonical)
    reason = (ReasonCode.HTTP_NOT_PERMITTED if scheme == "http"
              else ReasonCode.PUBLIC_URL_CANDIDATE)
    return UrlDecision(
        original_url=value, decision=Decision.REVIEW if scheme == "http" else Decision.ACCEPT,
        reason_code=reason, policy_version=_VERSION, canonical_url=canonical,
        host=host, host_kind=kind,
        effective_port=443 if scheme == "https" or port is not None else 80,
        explanation=_MESSAGES[reason],
        requested_human_action=_REVIEW_ACTION if scheme == "http" else None,
    )
