# 02 — Source snapshots and provenance

Decision D2: **PENDING**. Approve the exact bytes and derivation scope below, not a moving URL.

Six unmodified XML registry downloads are design evidence only. They are not packaged as runtime resources, and no candidate URL was resolved or contacted. Retrieval date: 2026-09-25. Registry update dates differ from retrieval dates. Hashes are SHA-256 of the stored raw bytes, including whitespace.

| Snapshot | Registry updated | Records | SHA-256 |
| --- | --- | --- | --- |
| [snapshots/iana-ipv4-special-registry.xml](snapshots/iana-ipv4-special-registry.xml) | 2025-10-09 | 25 | `cf24e11f41b7d42c68debe2d18b97cac815084ec413ebb3b244f704028a16f20` |
| [snapshots/iana-ipv6-special-registry.xml](snapshots/iana-ipv6-special-registry.xml) | 2025-10-09 | 25 | `c17f4380ba84fb2160dae82ebfd8bd155a5853cfab624ed3a9fd251638a8be02` |
| [snapshots/ipv4-address-space.xml](snapshots/ipv4-address-space.xml) | 2025-10-10 | 256 | `8ca3774374c81e4a673bb12d0eb415e7ac9970c6f5a6ceb14106de64b2cb3dcd` |
| [snapshots/ipv6-address-space.xml](snapshots/ipv6-address-space.xml) | 2025-10-23 | 20 | `15481d1e549b481f3bd0321c5cd2c0327a00cbd3d5a6fc35fc7b53b51e70b1cb` |
| [snapshots/ipv6-unicast-address-assignments.xml](snapshots/ipv6-unicast-address-assignments.xml) | 2025-10-10 | 51 | `22f9a545e020ea6b9adea9ea0276f3157e32c838682459a45bfe7760de0aefc3` |
| [snapshots/special-use-domain-names.xml](snapshots/special-use-domain-names.xml) | 2026-05-22 | 42 | `2659dec6fdb0377ba1f12d7418eb34e38b312e5f739574aeb868e00e1bcdf1e4` |

## Source URLs

- [iana-ipv4-special-registry.xml](https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xml)
- [iana-ipv6-special-registry.xml](https://www.iana.org/assignments/iana-ipv6-special-registry/iana-ipv6-special-registry.xml)
- [ipv4-address-space.xml](https://www.iana.org/assignments/ipv4-address-space/ipv4-address-space.xml)
- [ipv6-address-space.xml](https://www.iana.org/assignments/ipv6-address-space/ipv6-address-space.xml)
- [ipv6-unicast-address-assignments.xml](https://www.iana.org/assignments/ipv6-unicast-address-assignments/ipv6-unicast-address-assignments.xml)
- [special-use-domain-names.xml](https://www.iana.org/assignments/special-use-domain-names/special-use-domain-names.xml)

## Exact transformations

1. Read IPv4/IPv6 special-purpose address fields; split comma-separated CIDRs, retain every row including terminated entries, normalise CIDR notation only. Do not honour globally-reachable exceptions. IPv4 adds `224.0.0.0/4` from multicast address-space assignments.
2. Select IPv6 global-unicast rows whose status is exactly ALLOCATED as eligibility; keep deny precedence. This is proposed D1a.
3. Take every special-use name, remove the display-only ` (DEPRECATED)` annotation and terminal root dot, lowercase, and retain the row. This source-data transformation does not permit trailing-dot input URLs.
4. Add the six explicitly listed local suffixes; remove redundant child entries only in the effective table. Preserve full source rows in JSON and XML.
5. Do not follow WHOIS/RDAP links, query DNS, inspect local services, infer a registrant, or fetch source candidates.

## Reproducibility and limits

[manifest.json](snapshots/manifest.json) records URLs, byte lengths, hashes and row counts. The review package pins the bytes; a later source update never changes a proposed rule automatically. A new snapshot requires a reviewed diff and version change. These are registry facts, not a statement that all remaining addresses are reachable or that a hostname is public. Policy citations support provenance; the conservative choice to reject every special-purpose entry belongs to ControlOps.
