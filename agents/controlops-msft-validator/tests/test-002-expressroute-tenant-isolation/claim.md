# Claim Record - Test 002

## Exact Claim

"Separate Microsoft Entra tenants automatically isolate Azure VNets connected to the same ExpressRoute circuit."

## Validation Question

Do separate Microsoft Entra tenants inherently prevent IP connectivity between Azure VNets that are both linked to the same ExpressRoute circuit?

## Start Time

- UTC: 2026-07-26T14:43:07Z
- Local (Europe/London): 2026-07-26_15-43-07_BST

## Material Assumptions

1. The claim refers to Azure ExpressRoute Private Peering, which is the peering type used for VNet-to-VNet connectivity.
2. "Automatically isolate" means no additional configuration (route filters, network security groups, firewall rules) is required or expected — isolation would be inherent solely from tenant separation.
3. The claim implies that tenant identity boundaries are equivalent to network-routing boundaries in the ExpressRoute control plane.
