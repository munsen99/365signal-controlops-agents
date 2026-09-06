"""Read-only public web search and extraction. GET/HEAD only. SSRF-closed.

The model may supply a search query or a public http(s) URL. It cannot
choose the search origin, HTTP method, headers, or follow private redirects.
Retrieved content is untrusted data and is never executed.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from collections import deque
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from aea.marketplace.protocol import MarketplaceError
from aea.marketplace.sanitise import HOSTILE_CONTENT, sanitise_marketplace_text, sanitise_web_text
from aea.policy.reasons import HttpCode

HTTP_TIMEOUT_SECONDS = 10.0
HTTP_BODY_MAX_BYTES = 262144
MAX_REDIRECTS = 3
MAX_RESULTS = 8
USER_AGENT = "aea-readonly-web/1"
SEARCH_ORIGIN = "https://lite.duckduckgo.com"
SEARCH_PATH = "/lite/"
SEARCH_ORIGINS = frozenset({SEARCH_ORIGIN, "https://html.duckduckgo.com"})
ALLOWED_SCHEMES = frozenset({"http", "https"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE", "CONNECT", "TRACE", "OPTIONS"})
SAFE_METHODS = frozenset({"GET", "HEAD"})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "application/json",
        "application/problem+json",
    }
)
CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "bearer",
        "private_key",
        "seed",
        "mnemonic",
    }
)
BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".lan")
BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "metadata.google.internal",
        "host.docker.internal",
    }
)
_RESULT_HREF = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r"""([^\s=]+)\s*=\s*("([^"]*)"|'([^']*)')""")
_SNIPPET_LITE = re.compile(
    r"""<(?:td|a)[^>]+class=['"][^'"]*result-snippet[^'"]*['"][^>]*>(.*?)</(?:td|a)>""",
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")
_AD_SKIP = re.compile(r"y\.js|ad_provider|ads-by-microsoft|duckduckgo-help-pages", re.I)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "iframe"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "iframe"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def _default_resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MarketplaceError(HttpCode.FORBIDDEN, "web destination could not be resolved") from exc
    addresses = []
    for info in infos:
        addr = info[4][0]
        if addr not in addresses:
            addresses.append(addr)
    if not addresses:
        raise MarketplaceError(HttpCode.FORBIDDEN, "web destination could not be resolved")
    return addresses


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        return _blocked_ip(ip.ipv4_mapped)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _strip_tags(value: str) -> str:
    return _TAG.sub(" ", value.replace("&amp;", "&").replace("&quot;", '"'))


def extract_visible_text(html: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed web content") from exc
    return " ".join(parser.parts)


class ReadOnlyWebService:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Callable[[str], list[str]] = _default_resolve,
        now: Callable[[], float] = time.time,
        searches_per_hour: int = 20,
        extracts_per_hour: int = 20,
    ) -> None:
        self._owns = client is None
        self._client = client or httpx.Client(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/json, text/plain"},
        )
        self._resolve = resolver
        self._now = now
        self._search_times: deque[float] = deque()
        self._extract_times: deque[float] = deque()
        self._search_limit = searches_per_hour
        self._extract_limit = extracts_per_hour

    @staticmethod
    def _encode_search_url(query: str) -> str:
        return f"{SEARCH_ORIGIN}{SEARCH_PATH}?{urlencode({'q': query})}"

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def request(self, method: str, *_args: object, **_kwargs: object) -> None:
        if method.upper() in MUTATING_METHODS or method.upper() not in SAFE_METHODS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "web research is GET/HEAD only")
        raise MarketplaceError(HttpCode.FORBIDDEN, "web research is GET/HEAD only")

    def web_search(self, *, query: str, limit: int = 5) -> dict[str, Any]:
        self._rate(self._search_times, self._search_limit, "web search rate limit exceeded")
        safe = sanitise_marketplace_text(query)
        if safe.prompt_injection:
            raise MarketplaceError(HttpCode.PROMPT_INJECTION_DETECTED, "unsafe web search query")
        cap = max(1, min(limit, MAX_RESULTS))
        encoded = self._encode_search_url(safe.preview)
        payload = self._get(encoded, allow_search_origin=True)
        results = self._parse_search(payload["body"], cap)
        self._search_times.append(self._now())
        return {
            "ok": True,
            "code": HttpCode.OK,
            "query": safe.preview,
            "provider": "duckduckgo",
            "untrusted": True,
            "read_only": True,
            "results": results,
        }

    def web_extract(self, *, url: str) -> dict[str, Any]:
        self._rate(self._extract_times, self._extract_limit, "web extract rate limit exceeded")
        current = self.validate_public_http_url(url)
        payload = self._get(current)
        text = payload["body"]
        ctype = payload["content_type"]
        if ctype in {"text/html", "application/xhtml+xml"}:
            visible = extract_visible_text(text)
        else:
            visible = text
        wrapped = sanitise_web_text(visible)
        classification = HOSTILE_CONTENT if wrapped.prompt_injection else None
        self._extract_times.append(self._now())
        return {
            "ok": True,
            "code": HttpCode.OK,
            "url": current,
            "final_url": payload["url"],
            "content_type": ctype,
            "title": None,
            "text": wrapped.wrapped,
            "untrusted": True,
            "read_only": True,
            "classification": classification,
            "flags": list(wrapped.flags),
        }

    def validate_public_http_url(self, raw: str, *, allow_search_origin: bool = False) -> str:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 2048:
            raise MarketplaceError(HttpCode.FORBIDDEN, "web URL rejected")
        if any(ch.isspace() for ch in raw):
            raise MarketplaceError(HttpCode.FORBIDDEN, "web URL rejected")
        parsed = urlsplit(raw.strip())
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            raise MarketplaceError(HttpCode.FORBIDDEN, "arbitrary non-http scheme rejected")
        if parsed.username is not None or parsed.password is not None:
            raise MarketplaceError(HttpCode.FORBIDDEN, "credential-bearing URL rejected")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
            raise MarketplaceError(HttpCode.FORBIDDEN, "private/local address rejected")
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(key.lower() in CREDENTIAL_QUERY_KEYS for key in query):
            raise MarketplaceError(HttpCode.FORBIDDEN, "credential-bearing URL rejected")
        literal = _ip(host)
        if literal is None:
            try:
                literal = ipaddress.IPv4Address(socket.inet_aton(host))
            except OSError:
                literal = None
        if literal is not None:
            if _blocked_ip(literal):
                raise MarketplaceError(HttpCode.FORBIDDEN, "private/local address rejected")
        else:
            origin = f"{parsed.scheme.lower()}://{host}"
            if allow_search_origin and origin in SEARCH_ORIGINS:
                return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
            for address in self._resolve(host):
                ip = _ip(address)
                if ip is None or _blocked_ip(ip):
                    raise MarketplaceError(HttpCode.FORBIDDEN, "private/local address rejected")
        if parsed.port in {18700, 18701, 18702, 18703, 18704, 18705, 9119} and literal is not None and _blocked_ip(literal):
            raise MarketplaceError(HttpCode.FORBIDDEN, "control-plane endpoint rejected")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))

    def _rate(self, bucket: deque[float], limit: int, message: str) -> None:
        now = self._now()
        cutoff = now - 3600
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise MarketplaceError(HttpCode.FORBIDDEN, message)

    def _get(self, url: str, *, allow_search_origin: bool = False) -> dict[str, str]:
        current = self.validate_public_http_url(url, allow_search_origin=allow_search_origin)
        hops = 0
        while True:
            host = urlsplit(current).hostname or "web-origin"
            try:
                response = self._client.request(
                    "GET",
                    current,
                    timeout=HTTP_TIMEOUT_SECONDS,
                    follow_redirects=False,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html, application/xhtml+xml, text/plain, application/json",
                    },
                )
            except httpx.TimeoutException as exc:
                raise MarketplaceError(HttpCode.TIMEOUT, f"web research timed out contacting {host}") from exc
            except httpx.HTTPError as exc:
                raise MarketplaceError(
                    HttpCode.NETWORK_FAILURE,
                    f"web research transport failed contacting {host}",
                ) from exc
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location:
                    raise MarketplaceError(HttpCode.FORBIDDEN, "web redirect rejected")
                hops += 1
                if hops > MAX_REDIRECTS:
                    raise MarketplaceError(HttpCode.FORBIDDEN, "web redirect rejected")
                nxt = urljoin(current, location)
                current = self.validate_public_http_url(nxt)
                continue
            if response.status_code == 202:
                raise MarketplaceError(
                    HttpCode.MARKETPLACE_UNAVAILABLE,
                    f"search origin HTTP 202 challenge from {host}",
                )
            if response.status_code >= 400:
                if response.status_code == 404:
                    code = HttpCode.NOT_FOUND
                elif response.status_code >= 500:
                    code = HttpCode.MARKETPLACE_UNAVAILABLE
                else:
                    code = HttpCode.FORBIDDEN
                raise MarketplaceError(code, f"web research HTTP {response.status_code} from {host}")
            if len(response.content) > HTTP_BODY_MAX_BYTES:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "web response too large")
            ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype not in ALLOWED_CONTENT_TYPES:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "web content-type rejected")
            try:
                body = response.content.decode("utf-8", errors="replace")
            except Exception as exc:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed web content") from exc
            final = str(getattr(response, "url", current) or current)
            return {"body": body, "content_type": ctype, "url": final}

    def _parse_search(self, html: str, limit: int) -> list[dict[str, Any]]:
        if not isinstance(html, str):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed search result")
        pairs = _RESULT_HREF.findall(html)
        if not pairs:
            pairs = _lite_result_pairs(html)
        snippets = [_strip_tags(item).strip() for item in _SNIPPET.findall(html)]
        if not snippets:
            snippets = [_strip_tags(item).strip() for item in _SNIPPET_LITE.findall(html)]
        results: list[dict[str, Any]] = []
        for index, (href, title_html) in enumerate(pairs):
            if len(results) >= limit:
                break
            title_plain = _strip_tags(title_html).strip()
            if title_plain.lower() in {"more info", "more information"}:
                continue
            resolved = self._unwrap_search_url(unquote(href.strip().replace("&amp;", "&")))
            if _AD_SKIP.search(resolved):
                continue
            try:
                safe_url = self.validate_public_http_url(resolved)
            except MarketplaceError:
                continue
            title = sanitise_web_text(title_plain, max_chars=200)
            snippet_raw = snippets[index] if index < len(snippets) else ""
            snippet = sanitise_web_text(snippet_raw, max_chars=400)
            hostile = title.prompt_injection or snippet.prompt_injection
            results.append(
                {
                    "title": title.wrapped,
                    "url": safe_url,
                    "snippet": snippet.wrapped,
                    "untrusted": True,
                    "classification": HOSTILE_CONTENT if hostile else None,
                    "flags": sorted(set(title.flags + snippet.flags)),
                }
            )
        return results

    def _unwrap_search_url(self, href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlsplit(href.replace("&amp;", "&"))
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
        return href


def _anchor_attrs(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR.finditer(blob):
        value = match.group(3) if match.group(3) is not None else match.group(4)
        out[match.group(1).lower()] = value or ""
    return out


def _lite_result_pairs(html: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for attrs_blob, inner in _ANCHOR.findall(html):
        attrs = _anchor_attrs(attrs_blob)
        classes = attrs.get("class") or ""
        if "result-link" not in classes and "result__a" not in classes:
            continue
        href = attrs.get("href") or ""
        if not href:
            continue
        pairs.append((href, inner))
    return pairs
