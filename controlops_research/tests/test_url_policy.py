"""Approved PR1 vectors plus independent semantic, isolation and interface checks."""

import ast
import csv
from dataclasses import FrozenInstanceError, asdict, fields
from enum import StrEnum
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

from controlops_research import policy, policy_data
from controlops_research.policy import Decision, ReasonCode, UrlDecision, evaluate_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "url_policy"
DESIGN = ROOT / "docs" / "prs" / "PR1-implementation-design"
EXAMPLES = json.loads((FIXTURES / "decision-examples.json").read_text())
NAMES = json.loads((FIXTURES / "namespace-boundaries.json").read_text())
with (FIXTURES / "address-boundaries.csv").open(newline="") as handle:
    ADDRESSES = list(csv.DictReader(handle))


@pytest.mark.parametrize("case", EXAMPLES, ids=lambda case: case["id"])
def test_approved_decision_examples(case, monkeypatch):
    if not case["policy_available"]:
        monkeypatch.delattr(policy_data, "IPV4_DENY")
    assert asdict(evaluate_url(case["input"])) == case["expected"]


@pytest.mark.parametrize("case", ADDRESSES, ids=lambda case: case["id"])
def test_approved_address_boundaries(case):
    result = evaluate_url(case["url"])
    assert result.decision.value == case["decision"]
    assert result.reason_code.value == case["reason_code"]


@pytest.mark.parametrize("case", NAMES, ids=lambda case: case["url"])
def test_approved_namespace_boundaries(case):
    result = evaluate_url(case["url"])
    assert result.decision.value == case["decision"]
    assert result.reason_code.value == case["reason_code"]


# Expand the complete parent matrix independently of implementation constants.
PARENT_MATRIX = [
    ("https://learn.microsoft.com/", "PUBLIC_URL_CANDIDATE"),
    ("HTTPS://LEARN.MICROSOFT.COM:443", "PUBLIC_URL_CANDIDATE"),
    ("https://8.8.8.8/", "PUBLIC_URL_CANDIDATE"),
    ("https://[2606:4700:4700::1111]/", "PUBLIC_URL_CANDIDATE"),
    ("http://learn.microsoft.com/", "HTTP_NOT_PERMITTED"),
    ("http://learn.microsoft.com:443/", "HTTP_NOT_PERMITTED"),
    ("http://learn.microsoft.com:80/", "PORT_NOT_PERMITTED"),
    ("http://127.0.0.1/", "DESTINATION_PROHIBITED"),
    ("http://user@learn.microsoft.com/", "USERINFO_FORBIDDEN"),
    ("http://learn.microsoft.com/%ZZ", "MALFORMED_PERCENT_ESCAPE"),
    *[(f"https://{name}/", "HOST_NOT_PERMITTED") for name in (
        "localhost", "hermes", "postgres", "economic-control", "lm-studio",
        "controlops-msft-validator", "2130706433", "0x7f000001", "0177.0.0.1",
        "127.1", "xn--bcher-kva.de", "learn.microsoft.com.", "a..com", "-a.com", "a_b.com",
    )],
    *[(f"https://{host}/", "DESTINATION_PROHIBITED") for host in (
        "a.localhost", "printer.local", "host.internal", "host.test", "host.invalid",
        "example.com", "127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.0.1",
        "192.168.1.1", "169.254.169.254", "100.64.0.1", "198.18.0.1", "192.0.2.1",
        "0.0.0.0", "224.0.0.1", "240.0.0.1", "[::]", "[::1]", "[fc00::1]", "[fe80::1]",
        "[ff02::1]", "[2001:db8::1]", "[::ffff:c0a8:101]", "[::ffff:808:808]",
        "[64:ff9b::808:808]",
    )],
    ("https://[::ffff:192.168.1.1]/", "HOST_NOT_PERMITTED"),
    ("https://[fe80::1%25eth0]/", "ENCODED_AUTHORITY_FORBIDDEN"),
    *[(url, "USERINFO_FORBIDDEN") for url in (
        "https://user@learn.microsoft.com/", "https://user:pass@learn.microsoft.com/",
        "https://@learn.microsoft.com/", "https://public.example@127.0.0.1/",
        "https://learn.microsoft.com%2F@127.0.0.1/",
    )],
    *[(f"https://learn.microsoft.com:{port}/", "PORT_NOT_PERMITTED")
      for port in (80, 5432, 1234, 8443, 18700, 18701, 18702, 18703, 18704, 18705)],
    *[(f"https://learn.microsoft.com:{port}/", "INVALID_PORT")
      for port in ("", "0443", "+443", "0", "65536")],
    *[(url, "MALFORMED_URL") for url in (
        "file:///etc/passwd", "data:text/plain,x", "javascript:alert(1)", "mailto:a@b.com",
        "//learn.microsoft.com/", "/relative", "https:///path", "https://[::1/",
    )],
    *[(url, "UNSUPPORTED_SCHEME") for url in (
        "ftp://host.com/", "custom://host.com/", "file://host.com/path",
    )],
    ("", "INVALID_INPUT"), (None, "INVALID_INPUT"),
    ("https://bücher.de/", "FORBIDDEN_RAW_CHARACTER"),
    ("https://%31%32%37.0.0.1/", "ENCODED_AUTHORITY_FORBIDDEN"),
    (" https://learn.microsoft.com/", "FORBIDDEN_RAW_CHARACTER"),
    ("https://learn.microsoft.com/\n", "FORBIDDEN_RAW_CHARACTER"),
    ("https://learn.microsoft.com\\@127.0.0.1/", "FORBIDDEN_RAW_CHARACTER"),
    ("https://learn.microsoft.com/%ZZ", "MALFORMED_PERCENT_ESCAPE"),
    ("https://learn.microsoft.com/%0D%0AHost:x", "FORBIDDEN_ENCODED_CHARACTER"),
    ("https://learn.microsoft.com/a/../b", "DOT_SEGMENT_FORBIDDEN"),
    ("https://learn.microsoft.com/a/%2e%2e/b", "DOT_SEGMENT_FORBIDDEN"),
    ("https://learn.microsoft.com/a%2fb?q=x%26y&q=Two#section", "PUBLIC_URL_CANDIDATE"),
    ("https://learn.microsoft.com/?next=http%3A%2F%2F127.0.0.1", "PUBLIC_URL_CANDIDATE"),
    ("https://learn.microsoft.com/?", "PUBLIC_URL_CANDIDATE"),
]


@pytest.mark.parametrize("value,code", PARENT_MATRIX)
def test_complete_parent_matrix(value, code):
    result = evaluate_url(value)
    assert result.reason_code.value == code
    expected = {"PUBLIC_URL_CANDIDATE": "ACCEPT", "HTTP_NOT_PERMITTED": "REVIEW"}.get(code, "REJECT")
    assert result.decision.value == expected


def test_approved_data_and_fixture_provenance():
    doc = json.loads((DESIGN / "proposed-policy-data.json").read_text())
    assert policy_data.POLICY_VERSION == doc["proposed_policy_version"]
    assert policy_data.IPV4_DENY == tuple(x["cidr"] for x in doc["ipv4_deny"])
    assert policy_data.IPV6_DENY == tuple(x["cidr"] for x in doc["ipv6_deny"])
    assert policy_data.IPV6_ELIGIBILITY == tuple(doc["ipv6_eligibility"])
    assert policy_data.NAMESPACE_DENY == tuple(doc["effective_namespace_deny"])
    manifest = json.loads((DESIGN / "package-manifest.json").read_text())
    for entry in manifest["artifacts"] + manifest["authoritative_inputs"]:
        assert hashlib.sha256((DESIGN / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
    for path in FIXTURES.iterdir():
        assert path.read_bytes() == (DESIGN / "fixtures" / path.name).read_bytes()


@pytest.mark.parametrize("value", [case["input"] for case in EXAMPLES if case["expected"]["decision"] != "REJECT"])
def test_repeatability_and_canonicalisation_idempotence(value):
    first = evaluate_url(value)
    assert evaluate_url(value) == first
    second = evaluate_url(first.canonical_url)
    assert first.canonical_url == second.canonical_url
    assert first.decision == second.decision
    assert first.reason_code == second.reason_code
    assert (first.host, first.host_kind, first.effective_port) == (second.host, second.host_kind, second.effective_port)


@pytest.mark.parametrize("value,canonical", [
    ("https://learn.microsoft.com?", "https://learn.microsoft.com/?"),
    ("https://learn.microsoft.com/?a=&a=Two&a=%7e+%20#", "https://learn.microsoft.com/?a=&a=Two&a=%7E+%20"),
    ("https://learn.microsoft.com/a//b;Q?x=1&x=2#fragment?ok", "https://learn.microsoft.com/a//b;Q?x=1&x=2"),
    ("http://LEARN.MICROSOFT.COM:443?", "http://learn.microsoft.com:443/?"),
    ("https://learn.microsoft.com/%252e%252e/%2f?q=%40%3a", "https://learn.microsoft.com/%252e%252e/%2F?q=%40%3A"),
])
def test_component_semantics(value, canonical):
    assert evaluate_url(value).canonical_url == canonical


@pytest.mark.parametrize("path", ["/.", "/..", "/a/../b", "/%2e", "/.%2E", "/%2e.", "/a/%2E%2e/"])
def test_dot_segment_spellings(path):
    assert evaluate_url("https://learn.microsoft.com" + path).reason_code is ReasonCode.DOT_SEGMENT_FORBIDDEN


@pytest.mark.parametrize("host,code", [
    ("a.com", "PUBLIC_URL_CANDIDATE"),
    ("a" * 63 + ".com", "PUBLIC_URL_CANDIDATE"),
    ("a" * 64 + ".com", "HOST_NOT_PERMITTED"),
    (".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61]), "PUBLIC_URL_CANDIDATE"),
    (".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 62]), "HOST_NOT_PERMITTED"),
    ("learn.microsoft.c", "HOST_NOT_PERMITTED"),
    ("a.123", "HOST_NOT_PERMITTED"), ("a.xn--p1ai", "HOST_NOT_PERMITTED"),
    ("a-.com", "HOST_NOT_PERMITTED"), ("a.onion", "DESTINATION_PROHIBITED"),
    ("localhost.com", "PUBLIC_URL_CANDIDATE"), ("notexample.com", "PUBLIC_URL_CANDIDATE"),
])
def test_hostname_boundaries(host, code):
    assert evaluate_url("https://" + host + "/").reason_code.value == code


@pytest.mark.parametrize("host,code", [
    ("2606:4700::1:0:0:2", "PUBLIC_URL_CANDIDATE"),  # first zero run wins tie
    ("2606:4700:0:0:1::2", "HOST_NOT_PERMITTED"),
    ("2606:4700::1:0:2", "PUBLIC_URL_CANDIDATE"),  # longest run
    ("2606:4700:4700:1:0:2:3:4", "PUBLIC_URL_CANDIDATE"),
    ("2606:4700:4700:1::2:3:4", "HOST_NOT_PERMITTED"),  # single zero
    ("2606:4700:4700::01", "HOST_NOT_PERMITTED"),
    ("2606:4700:4700::ABCD", "HOST_NOT_PERMITTED"),
    ("v1.fe80", "HOST_NOT_PERMITTED"),
    ("::ffff:0:0", "DESTINATION_PROHIBITED"),
    ("::ffff:ffff:ffff", "DESTINATION_PROHIBITED"),
    ("::ffff:0.0.0.0", "HOST_NOT_PERMITTED"),
    ("::ffff:255.255.255.255", "HOST_NOT_PERMITTED"),
    ("2000::1", "DESTINATION_PROHIBITED"), ("2001:1000::1", "DESTINATION_PROHIBITED"),
    ("3ffe::1", "DESTINATION_PROHIBITED"), ("2001:1::1", "DESTINATION_PROHIBITED"),
    ("2002::1", "DESTINATION_PROHIBITED"),
])
def test_ipv6_spelling_and_deny_precedence(host, code):
    assert evaluate_url("https://[" + host + "]/").reason_code.value == code


@pytest.mark.parametrize("value,code", [
    ("https://user@127.0.0.1:80/%2e", "USERINFO_FORBIDDEN"),
    ("http://127.0.0.1:80/", "PORT_NOT_PERMITTED"),
    ("https://127.0.0.1/%2e", "DESTINATION_PROHIBITED"),
    ("http://learn.microsoft.com/%00%ZZ", "MALFORMED_PERCENT_ESCAPE"),
    ("http://learn.microsoft.com/ %ZZ", "FORBIDDEN_RAW_CHARACTER"),
    ("https://user@host.com:65536/", "USERINFO_FORBIDDEN"),
    ("ftp://user@host.com/", "UNSUPPORTED_SCHEME"),
    ("https://host.com/{bad}/..", "INVALID_COMPONENT"),
    ("https://host.com/#%00", "FORBIDDEN_ENCODED_CHARACTER"),
    ("https://host.com/#raw#hash", "INVALID_COMPONENT"),
    ("https://host.com/#%", "MALFORMED_PERCENT_ESCAPE"),
    ("https://host.com:999999999999999999999999999/", "INVALID_PORT"),
    ("https://[::1]junk/", "MALFORMED_URL"),
    ("https://[[::1]]/", "MALFORMED_URL"),
    ("https://[]/", "MALFORMED_URL"),
    ("https://2606:4700:4700::1111/", "MALFORMED_URL"),
])
def test_validation_precedence_and_parser_ambiguity(value, code):
    assert evaluate_url(value).reason_code.value == code


class HostileObject:
    def __str__(self):
        raise AssertionError("Input conversion is forbidden")

    def __repr__(self):
        raise AssertionError("Input repr is forbidden")

    def __bool__(self):
        raise AssertionError("Input truth evaluation is forbidden")


class HostileString(str):
    def __str__(self):
        raise AssertionError("Subclass conversion is forbidden")

    def __len__(self):
        raise AssertionError("Subclass methods are forbidden")

    def __iter__(self):
        raise AssertionError("Subclass methods are forbidden")


@pytest.mark.parametrize("factory", [
    lambda: b"https://learn.microsoft.com/", lambda: True, lambda: [], lambda: {},
    HostileObject, lambda: HostileString("https://learn.microsoft.com/"),
], ids=["bytes", "bool", "list", "dict", "object", "str-subclass"])
def test_exact_builtin_str_only(factory):
    result = evaluate_url(factory())
    assert result.reason_code is ReasonCode.INVALID_INPUT
    assert result.original_url is None


@pytest.mark.parametrize("value", ["https://learn.microsoft.com/", "http://learn.microsoft.com/", "https://user:secret@host.com/"])
def test_immutable_result_and_bool_protection(value):
    result = evaluate_url(value)
    with pytest.raises(TypeError):
        bool(result)
    with pytest.raises(FrozenInstanceError):
        result.decision = Decision.ACCEPT
    with pytest.raises(FrozenInstanceError):
        del result.policy_version
    assert not hasattr(result, "__dict__")
    assert "secret" not in repr(result)
    assert "original_url=" not in repr(result)


def test_closed_enums_interface_and_exact_fields():
    assert issubclass(Decision, StrEnum) and issubclass(ReasonCode, StrEnum)
    assert set(Decision) == {"ACCEPT", "REVIEW", "REJECT"}
    assert {code.value for code in ReasonCode} == {case["expected"]["reason_code"] for case in EXAMPLES}
    assert {x.name for x in fields(UrlDecision)} == set(EXAMPLES[0]["expected"])
    assert list(inspect.signature(evaluate_url).parameters) == ["value"]
    for enum in (Decision, ReasonCode):
        with pytest.raises(ValueError):
            enum("ALLOW_ANYTHING")
    with pytest.raises(TypeError):
        evaluate_url("https://learn.microsoft.com/", policy_version="older")


@pytest.mark.parametrize("name,replacement", [
    ("POLICY_VERSION", None), ("POLICY_VERSION", "controlops-public-url/v0.9.0"),
    ("IPV4_DENY", ()), ("IPV4_DENY", ("not-a-network",)),
    ("IPV4_DENY", ("0.0.0.0/8",)),  # valid CIDR but missing approved coverage
    ("IPV6_ELIGIBILITY", ("2000::/3",)),  # superseded rule must not reactivate
    ("IPV6_DENY", []), ("NAMESPACE_DENY", ("localhost",)),
    ("NAMESPACE_DENY", ("ü",)), ("NAMESPACE_DENY", (HostileObject(),)),
], ids=["missing-version", "wrong-version", "empty", "invalid-cidr", "missing-coverage", "broad-v6", "mutable", "missing-names", "non-ascii", "hostile-data"])
def test_corrupt_policy_fails_closed_before_input(name, replacement, monkeypatch):
    monkeypatch.setattr(policy_data, name, replacement)
    for value in ("https://learn.microsoft.com/", "http://learn.microsoft.com/", HostileObject()):
        result = evaluate_url(value)
        assert result.reason_code is ReasonCode.POLICY_UNAVAILABLE
        assert result.policy_version is None
        assert result.canonical_url is None


def test_missing_policy_fails_closed(monkeypatch):
    monkeypatch.delattr(policy_data, "NAMESPACE_DENY")
    assert evaluate_url("https://learn.microsoft.com/").reason_code is ReasonCode.POLICY_UNAVAILABLE


def test_no_global_private_classification_shortcuts(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Interpreter classification is not policy")
    from ipaddress import IPv4Address, IPv6Address
    for cls in (IPv4Address, IPv6Address):
        for attr in ("is_private", "is_global", "is_reserved", "is_loopback", "is_link_local"):
            monkeypatch.setattr(cls, attr, property(forbidden))
    assert evaluate_url("https://8.8.8.8/").decision is Decision.ACCEPT
    assert evaluate_url("https://[2606:4700:4700::1111]/").decision is Decision.ACCEPT
    assert evaluate_url("https://[2001:1::1]/").decision is Decision.REJECT


def test_policy_has_only_pure_dependencies():
    allowed = {"dataclasses", "enum", "hashlib", "ipaddress", "re", "types"}
    for name in ("policy.py", "policy_data.py"):
        tree = ast.parse((ROOT / "src" / "controlops_research" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(x.name in allowed for x in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1 and node.module is None
                    assert [x.name for x in node.names] == ["policy_data"]
                else:
                    assert node.module in allowed


def test_policy_import_and_evaluation_have_no_external_side_effects(tmp_path):
    # Separate interpreter: guards cannot be accidentally bypassed by cached
    # policy modules or disabled early by a pytest plugin.
    code = r'''
import sys, os, time, random, logging, datetime, socket, subprocess
from dataclasses import asdict
import enum, hashlib, ipaddress, re, types
import importlib.util

# Prime importlib's directory caches without executing either policy module.
# The package __init__ import itself has a separate PR0 isolation regression.
assert importlib.util.find_spec("controlops_research.policy") is not None
assert importlib.util.find_spec("controlops_research.policy_data") is not None
assert "controlops_research.policy" not in sys.modules
assert "controlops_research.policy_data" not in sys.modules

phase = "import"
def blocked(*args, **kwargs):
    raise AssertionError("Forbidden external/time/random/config operation")
def audit(event, args):
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in {
        "os.system", "os.fork", "os.posix_spawn", "os.listdir", "os.scandir",
        "os.remove", "os.rename", "os.mkdir", "os.putenv", "os.unsetenv"
    }:
        blocked()
    if event == "open":
        if phase != "import" or not str(args[0]).endswith((".py", ".pyc")):
            blocked()
    if phase == "evaluate" and event == "import":
        blocked()
sys.addaudithook(audit)
import controlops_research.policy as p
phase = "evaluate"
class NoEnvironment:
    __getitem__ = __iter__ = __len__ = get = blocked
os.environ = NoEnvironment()
os.getenv = os.urandom = blocked
for name in ("time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "sleep"):
    setattr(time, name, blocked)
for name in ("random", "randint", "randrange", "choice", "getrandbits"):
    setattr(random, name, blocked)
class NoDateTime(datetime.datetime):
    now = utcnow = today = blocked
class NoDate(datetime.date):
    today = blocked
datetime.datetime, datetime.date = NoDateTime, NoDate
logging.Logger._log = blocked
socket.getaddrinfo = socket.gethostbyname = socket.gethostbyname_ex = blocked
socket.socket = socket.create_connection = blocked
subprocess.Popen = blocked
'''
    # Run all approved URL vectors under the same evaluation guards.
    cases = [c for c in EXAMPLES if c["policy_available"]]
    code += "\nexamples = " + repr(cases) + "\n"
    code += "for c in examples:\n    assert asdict(p.evaluate_url(c['input'])) == c['expected']\n"
    code += "\nurls = " + repr([c["url"] for c in ADDRESSES + NAMES]) + "\n"
    code += "for url in urls:\n    p.evaluate_url(url)\n"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == result.stderr == ""
