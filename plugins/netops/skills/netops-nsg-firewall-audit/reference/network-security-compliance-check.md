# Skill: Compliance Check (nsec_compliance-check)

Validate network security controls against CIS Benchmarks, PCI-DSS, and NIST 800-53 requirements. This skill provides audit checklists, specific control mappings, and remediation guidance.

---

## CIS Benchmark — Networking Sections

### CIS Azure Foundations Benchmark (v2.1+)

| Control ID | Title | Check |
|-----------|-------|-------|
| 6.1 | Ensure that RDP access from the Internet is evaluated and restricted | No NSG inbound rule allowing TCP 3389 from 0.0.0.0/0 or Internet service tag |
| 6.2 | Ensure that SSH access from the Internet is evaluated and restricted | No NSG inbound rule allowing TCP 22 from 0.0.0.0/0 or Internet service tag |
| 6.3 | Ensure no Network Security Groups allow ingress from 0.0.0.0/0 to any port | Audit all NSG rules with source 0.0.0.0/0 or * |
| 6.4 | Ensure that UDP access from the Internet is restricted | No inbound UDP rules from 0.0.0.0/0 |
| 6.5 | Ensure that Network Watcher is enabled | Network Watcher provisioned in all active regions |
| 6.6 | Ensure that Azure flow logging uses VNet flow logs | VNet flow logs enabled for monitored VNets; existing NSG flow logs have documented migration plan before retirement: https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-migrate |

### CIS AWS Foundations Benchmark (v3.0+)

| Control ID | Title | Check |
|-----------|-------|-------|
| 5.1 | Ensure no Security Groups allow ingress from 0.0.0.0/0 to port 22 | `aws ec2 describe-security-groups` — no SG with SSH from 0.0.0.0/0 |
| 5.2 | Ensure no Security Groups allow ingress from 0.0.0.0/0 to port 3389 | No SG with RDP from 0.0.0.0/0 |
| 5.3 | Ensure no Security Groups allow ingress from ::/0 to port 22 | No IPv6 SSH from ::/0 |
| 5.4 | Ensure no Security Groups allow ingress from ::/0 to port 3389 | No IPv6 RDP from ::/0 |
| 5.5 | Ensure the default SG of every VPC restricts all traffic | Default SG: no inbound rules, no outbound rules |
| 3.9 | Ensure VPC flow logging is enabled in all VPCs | All VPCs have flow logs enabled |

### CIS GCP Foundations Benchmark (v3.0+)

| Control ID | Title | Check |
|-----------|-------|-------|
| 3.6 | Ensure that SSH access from the Internet is restricted | No firewall rule allowing TCP 22 from 0.0.0.0/0 |
| 3.7 | Ensure that RDP access from the Internet is restricted | No firewall rule allowing TCP 3389 from 0.0.0.0/0 |
| 3.8 | Ensure VPC Flow Logs are enabled for every subnet | Flow logs enabled on all subnets |
| 3.9 | Ensure no HTTPS or SSL proxy LB permits SSL policies with weak cipher suites | TLS 1.2+ minimum, no RC4/3DES |
| 3.10 | Ensure firewall rules log is enabled | Logging enabled on all firewall rules |

---

## PCI-DSS v4.0 — Network Controls

### Requirement 1: Install and Maintain Network Security Controls

| Sub-Requirement | Network Control | Cloud Implementation |
|----------------|----------------|---------------------|
| 1.2.1 | Restrict inbound/outbound traffic to that which is necessary | NSG/SG rules — default deny, explicit allow per application |
| 1.2.5 | All services, protocols, and ports allowed are identified, approved, and have business justification | Document all NSG/SG rules with justification. Remove unjustified rules |
| 1.3.1 | Inbound traffic from untrusted networks is restricted to CDE components | NSG/SG only allows internet traffic to web tier (443), not app/DB tiers |
| 1.3.2 | Outbound traffic from CDE is restricted | Outbound NSG/SG rules on CDE subnets — deny all except required destinations |
| 1.4.1 | NSCs between trusted and untrusted networks control traffic between CDE and other networks | Separate VNet/VPC for CDE with strict peering/routing controls |
| 1.4.2 | Inbound traffic from untrusted networks to CDE is restricted to necessary communications | WAF + NSG/SG layered filtering |

### Requirement 2: Apply Secure Configurations to All System Components

| Sub-Requirement | Network Control | Cloud Implementation |
|----------------|----------------|---------------------|
| 2.2.4 | Only necessary services, protocols, ports are enabled | Audit NSG/SG rules against application requirements. Remove unused |
| 2.2.7 | All non-console administrative access is encrypted | Ensure SSH (not Telnet), HTTPS (not HTTP), encrypted VPN for management |

### CDE Segmentation Validation
- CDE (Cardholder Data Environment) must be network-isolated from non-CDE workloads.
- Segmentation controls must be tested at least annually (penetration testing).
- Document all data flows into/out of the CDE with source, destination, protocol, port, and business justification.

---

## NIST 800-53 — Network Controls

### SC (System and Communications Protection) Family

| Control | Title | Cloud Implementation |
|---------|-------|---------------------|
| SC-7 | Boundary Protection | NSG/SG at subnet and NIC level. Azure Firewall / AWS Network Firewall at VNet/VPC boundary. Default deny posture. |
| SC-7(4) | External Telecommunications Services | ExpressRoute/Direct Connect for private connectivity. Encrypt all traffic over public internet (IPsec VPN, TLS). |
| SC-7(5) | Deny by Default / Allow by Exception | NSG/SG default deny inbound. Explicit allow rules with documented justification. |
| SC-7(8) | Route Traffic to Authenticated Proxy | Force web traffic through WAF/proxy. Azure Firewall application rules or AWS Network Firewall. |
| SC-8 | Transmission Confidentiality | TLS 1.2+ for all data in transit. IPsec for VPN tunnels. ExpressRoute MACsec for dedicated circuits. |
| SC-8(1) | Cryptographic Protection | AES-256 encryption for VPN. TLS 1.2+ with strong cipher suites (no RC4, 3DES, or NULL ciphers). |

### AC (Access Control) Family

| Control | Title | Cloud Implementation |
|---------|-------|---------------------|
| AC-4 | Information Flow Enforcement | NSG/SG rules enforce approved information flows. UDRs force traffic through inspection points. |
| AC-4(3) | Dynamic Information Flow Control | Azure Firewall threat intelligence. AWS Network Firewall IDS/IPS. Adaptive rules based on threat feeds. |
| AC-17 | Remote Access | VPN with MFA for remote access. Azure Bastion / AWS SSM Session Manager for privileged access. No direct RDP/SSH from internet. |

---

## Audit Checklist Format

### Standard Finding Template
```
Finding ID:      [Framework]-[Control]-[Number]
Severity:        Critical / High / Medium / Low / Informational
Framework:       CIS Azure 2.1 / PCI-DSS 4.0 / NIST 800-53 r5
Control:         [Control ID and Title]
Status:          PASS / FAIL / NOT APPLICABLE
Resource:        [Resource ID / ARN / name]
Description:     [What was found]
Evidence:        [CLI output or configuration snippet]
Remediation:     [Specific steps to fix]
Deadline:        [Based on severity: Critical=24h, High=7d, Medium=30d, Low=90d]
```

### Example Finding
```
Finding ID:      CIS-AZ-6.1-001
Severity:        Critical
Framework:       CIS Azure Foundations Benchmark v2.1
Control:         6.1 - RDP access from Internet restricted
Status:          FAIL
Resource:        /subscriptions/.../networkSecurityGroups/prod-nsg
Description:     NSG rule "AllowRDP" (priority 100) allows TCP 3389 
                 from source 0.0.0.0/0 (Internet)
Evidence:        az network nsg rule show --nsg-name prod-nsg -g MyRG -n AllowRDP
Remediation:     Restrict source to bastion subnet CIDR or remove rule. 
                 Use Azure Bastion for RDP access.
Deadline:        24 hours (Critical)
```
**Analysis only — verify against vendor documentation before applying.**
