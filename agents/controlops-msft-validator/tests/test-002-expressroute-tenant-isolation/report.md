# Validation Report - Test 002: ExpressRoute Cross-Tenant Network Isolation

## Claim

"Separate Microsoft Entra tenants automatically isolate Azure VNets connected to the same ExpressRoute circuit."

## Verdict

contradicted

## Confidence

high

## Summary

The claim is directly contradicted by authoritative Microsoft documentation. Separate Microsoft Entra tenants do not create network-level isolation between Azure VNets linked to the same ExpressRoute circuit. From a routing perspective, all VNets on the same ExpressRoute circuit share a single routing domain and can communicate with each other regardless of which tenant owns them. Identity separation (Microsoft Entra) is architecturally distinct from network-routing boundaries (ExpressRoute).

## Verified Facts

- Microsoft Learn states: "You can connect multiple virtual networks to the private peering domain" without any tenant restriction (MSFT-EV-001).
- Microsoft Learn FAQ directly answers: "Are virtual networks connected to the same circuit isolated from each other?" with "No. From a routing perspective, all virtual networks linked to the same ExpressRoute circuit are part of the same routing domain and aren't isolated from each other" (MSFT-EV-002).
- Microsoft Learn FAQ confirms: "Can virtual networks linked to the same ExpressRoute circuit talk to each other?" with "Yes. Virtual machines deployed in virtual networks connected to the same ExpressRoute circuit can communicate with each other" (MSFT-EV-002).

## Incorrect or Misleading Elements

- The claim asserts that separate Microsoft Entra tenants automatically provide network isolation. This is false — tenant boundaries are identity and administrative boundaries, not IP-routing boundaries.
- The claim conflates the Microsoft Entra control plane (identity, access management) with the Azure networking control plane (ExpressRoute routing domains). These are independent systems.

## Assumptions

1. The claim refers to ExpressRoute Private Peering, which is the peering type used for VNet-to-VNet connectivity.
2. "Automatically isolate" means no additional configuration beyond tenant separation would be needed to block traffic.

## Unresolved Questions

None. Two authoritative Microsoft sources directly and unambiguously contradict the claim.

## Sources

- MSFT-EV-001: Azure ExpressRoute: circuits and peering — https://learn.microsoft.com/en-us/azure/expressroute/expressroute-circuit-peerings
- MSFT-EV-002: Azure ExpressRoute FAQ — https://learn.microsoft.com/en-us/azure/expressroute/expressroute-faqs

## Review Required

yes
