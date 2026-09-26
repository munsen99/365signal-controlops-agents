# 01 — Proposed address and namespace tables

Decision D1: **PENDING**. This is proposed data, not an active policy.

Authoritative review data: [proposed-policy-data.json](proposed-policy-data.json). Source attribution and exact bytes are in [02](02-source-snapshots.md).

## Membership rules

After canonical host syntax validation: IPv4 is eligible only outside every IPv4 deny range. IPv6 must belong to a pinned ALLOCATED prefix below and to no IPv6 deny range. Deny wins over every overlap; globally reachable exceptions and terminated rows receive no exemption. No Python `is_private`/`is_global` policy decisions. All addresses outside eligibility fail closed.

**D1a — approve/reject explicitly:** tighten IPv6 eligibility from broad `2000::/3` to the pinned ALLOCATED rows. IANA states that unlisted space inside `2000::/3` is reserved. This catches `2000::1`, `2001:1000::1` and returned `3ffe::/16`, which broad-prefix-minus-special-purpose alone misses. Newly allocated space stays rejected until a reviewed revision. This is a stricter proposal, not a silently adopted spec change.

IPv4 allocation snapshot shows reserved /8s confined to local/private/loopback/multicast/future-use regions covered below. No current suballocation, route, ownership, or reachability claim is made. IPv6 allocation status likewise is not proof of a reachable host.

## Complete IPv4 deny entries

| CIDR | Basis |
| --- | --- |
| `0.0.0.0/8` | Pinned IPv4 special-purpose row |
| `0.0.0.0/32` | Pinned IPv4 special-purpose row |
| `10.0.0.0/8` | Pinned IPv4 special-purpose row |
| `100.64.0.0/10` | Pinned IPv4 special-purpose row |
| `127.0.0.0/8` | Pinned IPv4 special-purpose row |
| `169.254.0.0/16` | Pinned IPv4 special-purpose row |
| `172.16.0.0/12` | Pinned IPv4 special-purpose row |
| `192.0.0.0/24` | Pinned IPv4 special-purpose row |
| `192.0.0.0/29` | Pinned IPv4 special-purpose row |
| `192.0.0.8/32` | Pinned IPv4 special-purpose row |
| `192.0.0.9/32` | Pinned IPv4 special-purpose row |
| `192.0.0.10/32` | Pinned IPv4 special-purpose row |
| `192.0.0.170/32` | Pinned IPv4 special-purpose row |
| `192.0.0.171/32` | Pinned IPv4 special-purpose row |
| `192.0.2.0/24` | Pinned IPv4 special-purpose row |
| `192.31.196.0/24` | Pinned IPv4 special-purpose row |
| `192.52.193.0/24` | Pinned IPv4 special-purpose row |
| `192.88.99.0/24` | Pinned IPv4 special-purpose row |
| `192.88.99.2/32` | Pinned IPv4 special-purpose row |
| `192.168.0.0/16` | Pinned IPv4 special-purpose row |
| `192.175.48.0/24` | Pinned IPv4 special-purpose row |
| `198.18.0.0/15` | Pinned IPv4 special-purpose row |
| `198.51.100.0/24` | Pinned IPv4 special-purpose row |
| `203.0.113.0/24` | Pinned IPv4 special-purpose row |
| `240.0.0.0/4` | Pinned IPv4 special-purpose row |
| `255.255.255.255/32` | Pinned IPv4 special-purpose row |
| `224.0.0.0/4` | Local multicast exclusion backed by address-space registry |

The two NAT64 discovery addresses in one source row are expanded to separate /32 entries. Overlapping entries are retained for provenance, never interpreted as exceptions.

## Complete IPv6 deny entries

| CIDR | Basis |
| --- | --- |
| `::1/128` | Pinned IPv6 special-purpose row |
| `::/128` | Pinned IPv6 special-purpose row |
| `::ffff:0.0.0.0/96` | Pinned IPv6 special-purpose row |
| `64:ff9b::/96` | Pinned IPv6 special-purpose row |
| `64:ff9b:1::/48` | Pinned IPv6 special-purpose row |
| `100::/64` | Pinned IPv6 special-purpose row |
| `100:0:0:1::/64` | Pinned IPv6 special-purpose row |
| `2001::/23` | Pinned IPv6 special-purpose row |
| `2001::/32` | Pinned IPv6 special-purpose row |
| `2001:1::1/128` | Pinned IPv6 special-purpose row |
| `2001:1::2/128` | Pinned IPv6 special-purpose row |
| `2001:1::3/128` | Pinned IPv6 special-purpose row |
| `2001:2::/48` | Pinned IPv6 special-purpose row |
| `2001:3::/32` | Pinned IPv6 special-purpose row |
| `2001:4:112::/48` | Pinned IPv6 special-purpose row |
| `2001:10::/28` | Pinned IPv6 special-purpose row |
| `2001:20::/28` | Pinned IPv6 special-purpose row |
| `2001:30::/28` | Pinned IPv6 special-purpose row |
| `2001:db8::/32` | Pinned IPv6 special-purpose row |
| `2002::/16` | Pinned IPv6 special-purpose row |
| `2620:4f:8000::/48` | Pinned IPv6 special-purpose row |
| `3fff::/20` | Pinned IPv6 special-purpose row |
| `5f00::/16` | Pinned IPv6 special-purpose row |
| `fc00::/7` | Pinned IPv6 special-purpose row |
| `fe80::/10` | Pinned IPv6 special-purpose row |

Outside the eligibility table is rejected, including multicast, site-local, reserved and unassigned regions even when absent from the special-purpose table.

## Complete IPv6 eligibility entries

| Prefix | Rule |
| --- | --- |
| `2001::/23` | ALLOCATED snapshot row; deny wins |
| `2001:200::/23` | ALLOCATED snapshot row; deny wins |
| `2001:400::/23` | ALLOCATED snapshot row; deny wins |
| `2001:600::/23` | ALLOCATED snapshot row; deny wins |
| `2001:800::/22` | ALLOCATED snapshot row; deny wins |
| `2001:c00::/23` | ALLOCATED snapshot row; deny wins |
| `2001:e00::/23` | ALLOCATED snapshot row; deny wins |
| `2001:1200::/23` | ALLOCATED snapshot row; deny wins |
| `2001:1400::/22` | ALLOCATED snapshot row; deny wins |
| `2001:1800::/23` | ALLOCATED snapshot row; deny wins |
| `2001:1a00::/23` | ALLOCATED snapshot row; deny wins |
| `2001:1c00::/22` | ALLOCATED snapshot row; deny wins |
| `2001:2000::/19` | ALLOCATED snapshot row; deny wins |
| `2001:4000::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4200::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4400::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4600::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4800::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4a00::/23` | ALLOCATED snapshot row; deny wins |
| `2001:4c00::/23` | ALLOCATED snapshot row; deny wins |
| `2001:5000::/20` | ALLOCATED snapshot row; deny wins |
| `2001:8000::/19` | ALLOCATED snapshot row; deny wins |
| `2001:a000::/20` | ALLOCATED snapshot row; deny wins |
| `2001:b000::/20` | ALLOCATED snapshot row; deny wins |
| `2002::/16` | ALLOCATED snapshot row; deny wins |
| `2003::/18` | ALLOCATED snapshot row; deny wins |
| `2400::/12` | ALLOCATED snapshot row; deny wins |
| `2410::/12` | ALLOCATED snapshot row; deny wins |
| `2600::/12` | ALLOCATED snapshot row; deny wins |
| `2610::/23` | ALLOCATED snapshot row; deny wins |
| `2620::/23` | ALLOCATED snapshot row; deny wins |
| `2630::/12` | ALLOCATED snapshot row; deny wins |
| `2800::/12` | ALLOCATED snapshot row; deny wins |
| `2a00::/12` | ALLOCATED snapshot row; deny wins |
| `2a10::/12` | ALLOCATED snapshot row; deny wins |
| `2c00::/12` | ALLOCATED snapshot row; deny wins |

`2001::/23` and `2002::/16` are in both tables and remain entirely denied. No longest-prefix allow exception.

## Complete effective namespace deny table

| Name/suffix | Basis |
| --- | --- |
| `alt` | Pinned IANA special-use name |
| `arpa` | Local policy addition |
| `corp` | Local policy addition |
| `example` | Pinned IANA special-use name |
| `example.com` | Pinned IANA special-use name |
| `example.net` | Pinned IANA special-use name |
| `example.org` | Pinned IANA special-use name |
| `home` | Local policy addition |
| `internal` | Local policy addition |
| `intranet` | Local policy addition |
| `invalid` | Pinned IANA special-use name |
| `lan` | Local policy addition |
| `local` | Pinned IANA special-use name |
| `localhost` | Pinned IANA special-use name |
| `onion` | Pinned IANA special-use name |
| `test` | Pinned IANA special-use name |

Match lowercase `host == suffix` or `host.endswith("." + suffix)`. Single-label grammar rejection occurs earlier; e.g. `localhost` is HOST_NOT_PERMITTED, `a.localhost` is DESTINATION_PROHIBITED. All IANA source rows, including deprecated names, remain in JSON for audit. The broad local `arpa` exclusion subsumes its individual source names.

## Internal inventory and capability boundaries

Additional internal FQDNs: **empty — none supplied for this design**. No service/profile/secret discovery was performed. Single-label Hermes/Econo/validator names and listed local namespaces fail; an unknown internal FQDN on a public-looking domain can still pass syntax. This limitation is a future fetch/isolation gate, not assurance of completeness. Reviewers may supply explicit names for a revised proposal.

Only HTTPS omitted-port/443 can ACCEPT. HTTP omitted-port or explicit 443 can only REVIEW after every security check; explicit 80 and every other explicit port reject. IDN, trailing-dot, noncanonical IP and all userinfo restrictions are unchanged. Existing architecture invariants remain authoritative.
