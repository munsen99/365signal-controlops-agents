# Approved PR1 fixture amendment — 2026-09-25

Approved by the user through [Approved.txt](<../../Approved.txt>), continuing the
previous PR1 implementation authorisation. Scope: this fixture contradiction only.
No PR2 work, staging or commit is authorised.

Two boundary URL strings used dotted IPv4-mapped notation, which the approved
representation rule rejects as HOST_NOT_PERMITTED before address classification.
The boundary expectations instead intended to exercise DESTINATION_PROHIBITED.

| Original URL | Approved replacement URL | Expected reason (unchanged) |
| --- | --- | --- |
| `https://[::ffff:0.0.0.0]/` | `https://[::ffff:0:0]/` | DESTINATION_PROHIBITED |
| `https://[::ffff:255.255.255.255]/` | `https://[::ffff:ffff:ffff]/` | DESTINATION_PROHIBITED |

Only the URL fields changed; range/address columns retain their original numeric
address descriptions. The separate dotted mapped fixture remains unchanged and
expects HOST_NOT_PERMITTED. Policy tables, decisions, precedence and policy version
`controlops-public-url/v1.0.0` are unchanged: this corrects test inputs to the
already approved semantics, not policy behaviour.

## Hash evidence

- Original manifest SHA-256: `a6b93936931a85819e5ac2777be9e2b8480cb8ee0df19a943c97245085214c97`.
- Amended manifest SHA-256: `90e3b506ae26fc936b6822161d693b7f0c7507abff4b3c91b286a4e47d605278`.
- Original boundary fixture SHA-256: `bdad800192764b127c251e54ccac9b35667560c248abe9c5f0ae19f4c602955e`.
- Amended boundary fixture SHA-256: `1edadfe6de492d9b4263b3e84e33e4d073da1cf69432c8640d228018bc90557d`.
- Approval instruction SHA-256: `a548857fffec4fb5c86d6df6855753e3e39e2f2c21ddc80286a88c5c2183bf30`.

The [original manifest](previous-manifest.json) and
[original boundary CSV](previous-address-boundaries.csv) preserve exact historical
bytes. The [pre-implementation specification](PR1-public-url-policy-before-implementation.md)
also preserves the parent input pinned by the original review. The amended manifest
points to that archived parent input with its identical hash, so the canonical PR1
record can evolve during the explicitly authorised implementation without rewriting
historical evidence. Its revision/status and changed fixture hash are updated.
Other approved artifacts remain byte-identical. This record supplies the amendment
approval; historical pending labels in the submitted design remain historical.
