# Skill: Configuration Generation

## Purpose

Generate vendor-specific firewall configuration snippets from a policy intent description. Given a high-level requirement (e.g., "allow web servers in DMZ to reach DB servers on port 3306"), produce ready-to-review configuration for any of the 14 supported platforms.

---

## Input Requirements

Before generating configuration, gather:

| Parameter | Description | Example |
|-----------|-------------|---------|
| **Source zone** | Origin zone of the traffic | DMZ |
| **Source address** | IP/CIDR, FQDN, or address object | 10.1.2.0/24 or `DMZ_WebServers` |
| **Destination zone** | Target zone of the traffic | Database |
| **Destination address** | IP/CIDR, FQDN, or address object | 10.1.3.0/24 or `DB_Servers` |
| **Service/Port** | Protocol and port(s) | TCP/3306 |
| **Action** | allow / deny / drop / reject | allow |
| **Logging** | Enable session logging | yes |
| **Description** | Human-readable rule description | Allow DMZ web servers to MySQL |

---

## Vendor-Specific Configuration Templates

All examples implement the same policy intent:
> **Allow web servers in DMZ (10.1.2.0/24) to reach database servers (10.1.3.0/24) on TCP port 3306, with logging enabled.**

---

### 1. Azure Firewall (Bicep)

```bicep
// Network Rule Collection within a Firewall Policy
resource ruleCollectionGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2023-09-01' = {
  name: 'DMZ-to-Database'
  parent: firewallPolicy
  properties: {
    priority: 300
    ruleCollections: [
      {
        ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
        name: 'Allow-DMZ-to-DB'
        priority: 310
        action: {
          type: 'Allow'
        }
        rules: [
          {
            ruleType: 'NetworkRule'
            name: 'Allow-WebServers-MySQL'
            description: 'Allow DMZ web servers to MySQL'
            sourceAddresses: [ '10.1.2.0/24' ]
            destinationAddresses: [ '10.1.3.0/24' ]
            destinationPorts: [ '3306' ]
            ipProtocols: [ 'TCP' ]
          }
        ]
      }
    ]
  }
}
```

```bash
# Azure CLI equivalent
az network firewall policy rule-collection-group collection add-filter-collection \
  --policy-name myFirewallPolicy \
  --resource-group myRG \
  --rule-collection-group-name DMZ-to-Database \
  --name Allow-DMZ-to-DB \
  --collection-priority 310 \
  --action Allow \
  --rule-name Allow-WebServers-MySQL \
  --rule-type NetworkRule \
  --source-addresses "10.1.2.0/24" \
  --destination-addresses "10.1.3.0/24" \
  --destination-ports 3306 \
  --ip-protocols TCP
```

### 2. AWS Network Firewall (CloudFormation)

```yaml
# Stateful rule group
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  DMZtoDBRuleGroup:
    Type: AWS::NetworkFirewall::RuleGroup
    Properties:
      RuleGroupName: dmz-to-db-rules
      Type: STATEFUL
      Capacity: 10
      RuleGroup:
        RulesSource:
          StatefulRules:
            - Action: PASS
              Header:
                Protocol: TCP
                Source: "10.1.2.0/24"
                SourcePort: ANY
                Destination: "10.1.3.0/24"
                DestinationPort: "3306"
                Direction: FORWARD
              RuleOptions:
                - Keyword: "sid"
                  Settings: ["1000001"]
                - Keyword: "msg"
                  Settings: ['"Allow DMZ web servers to MySQL"']
```

```bash
# AWS CLI equivalent
aws network-firewall create-rule-group \
  --rule-group-name dmz-to-db-rules \
  --type STATEFUL \
  --capacity 10 \
  --rule-group '{
    "RulesSource": {
      "StatefulRules": [{
        "Action": "PASS",
        "Header": {
          "Protocol": "TCP",
          "Source": "10.1.2.0/24",
          "SourcePort": "ANY",
          "Destination": "10.1.3.0/24",
          "DestinationPort": "3306",
          "Direction": "FORWARD"
        },
        "RuleOptions": [
          {"Keyword": "sid", "Settings": ["1000001"]}
        ]
      }]
    }
  }'
```

### 3. GCP Cloud Firewall (gcloud)

```bash
# VPC firewall rule
gcloud compute firewall-rules create allow-dmz-to-db-mysql \
  --network=my-vpc \
  --priority=1000 \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:3306 \
  --source-ranges=10.1.2.0/24 \
  --destination-ranges=10.1.3.0/24 \
  --target-tags=db-servers \
  --enable-logging \
  --description="Allow DMZ web servers to MySQL"
```

### 4. Palo Alto Networks (PAN-OS set commands)

```
# Address objects
set address DMZ_WebServers ip-netmask 10.1.2.0/24
set address DB_Servers ip-netmask 10.1.3.0/24

# Service object
set service MySQL protocol tcp port 3306

# Security policy rule
set rulebase security rules "Allow-DMZ-to-DB-MySQL" from DMZ to Database source DMZ_WebServers destination DB_Servers application mysql service MySQL action allow log-end yes profile-setting group default-security-profiles
set rulebase security rules "Allow-DMZ-to-DB-MySQL" description "Allow DMZ web servers to MySQL"

# Commit
commit
```

### 5. Fortinet FortiGate (FortiOS CLI)

```
# Address objects
config firewall address
    edit "DMZ_WebServers"
        set subnet 10.1.2.0 255.255.255.0
    next
    edit "DB_Servers"
        set subnet 10.1.3.0 255.255.255.0
    next
end

# Service object
config firewall service custom
    edit "MySQL"
        set protocol TCP/UDP/SCTP
        set tcp-portrange 3306
    next
end

# Firewall policy
config firewall policy
    edit 0
        set name "Allow-DMZ-to-DB-MySQL"
        set srcintf "dmz"
        set dstintf "database"
        set srcaddr "DMZ_WebServers"
        set dstaddr "DB_Servers"
        set service "MySQL"
        set action accept
        set logtraffic all
        set comments "Allow DMZ web servers to MySQL"
    next
end
```

### 6. Check Point (mgmt_cli)

```bash
# Create host/network objects
mgmt_cli add network name "DMZ_WebServers" subnet "10.1.2.0" mask-length 24
mgmt_cli add network name "DB_Servers" subnet "10.1.3.0" mask-length 24

# Create service
mgmt_cli add service-tcp name "MySQL" port 3306

# Add access rule
mgmt_cli add access-rule layer "Network" \
  position top \
  name "Allow-DMZ-to-DB-MySQL" \
  source "DMZ_WebServers" \
  destination "DB_Servers" \
  service "MySQL" \
  action "Accept" \
  track "Log" \
  comments "Allow DMZ web servers to MySQL"

# Publish and install
mgmt_cli publish
mgmt_cli install-policy policy-package "Standard"
```

### 7. Cisco ASA (CLI)

```
! Address objects
object network DMZ_WebServers
 subnet 10.1.2.0 255.255.255.0
object network DB_Servers
 subnet 10.1.3.0 255.255.255.0

! Service object
object service MySQL
 service tcp destination eq 3306

! Access list
access-list DMZ_to_DB_ACL extended permit tcp object DMZ_WebServers object DB_Servers object MySQL log

! Apply to interface
access-group DMZ_to_DB_ACL in interface dmz
```

### 8. Juniper SRX (set commands)

```
# Address book entries
set security zones security-zone DMZ address-book address DMZ_WebServers 10.1.2.0/24
set security zones security-zone Database address-book address DB_Servers 10.1.3.0/24

# Application (or use junos-mysql if predefined)
set applications application MySQL protocol tcp destination-port 3306

# Security policy
set security policies from-zone DMZ to-zone Database policy Allow-DMZ-to-DB-MySQL match source-address DMZ_WebServers destination-address DB_Servers application MySQL
set security policies from-zone DMZ to-zone Database policy Allow-DMZ-to-DB-MySQL then permit
set security policies from-zone DMZ to-zone Database policy Allow-DMZ-to-DB-MySQL then log session-close

# Commit
commit
```

### 9. Zscaler (ZIA Firewall Filtering Rule)

ZIA firewall policy object names, fields, and API resource paths change over time. Prefer the ZIA Admin Portal or the current Zscaler API documentation instead of copying brittle endpoint examples; verify current `firewallFilteringRules` object names and required fields in the official firewall policy docs before generating automation.

**Policy intent mapping:**
- Rule name/description: `Allow-DMZ-to-DB-MySQL` / `Allow DMZ web servers to MySQL`
- Action/state: allow, enabled
- Source: DMZ web server IP group or location group
- Destination: `10.1.3.0/24` or approved destination object
- Application/service: MySQL / TCP destination port 3306
- Logging: full session logging if supported by the current tenant and license

> Note: Zscaler ZIA is primarily for internet-bound traffic. For internal east-west traffic like DMZ-to-DB, consider ZPA, Zscaler Cloud Connector, or a local firewall. Verify current API paths and fields in the official ZIA firewall policy documentation: https://help.zscaler.com/zia/firewall-policies

### 10. Sophos XG / XGS (CLI)

```
# Via device console
set firewall rule add
  name "Allow-DMZ-to-DB-MySQL"
  position top
  srczone DMZ
  dstzone Database
  src_net "10.1.2.0/255.255.255.0"
  dst_net "10.1.3.0/255.255.255.0"
  service "MySQL (TCP 3306)"
  action accept
  log enable
```

```json
// REST API equivalent
// POST /webconsole/APIController
{
  "reqxml": "<Request><Set operation='add'><FirewallRule><Name>Allow-DMZ-to-DB-MySQL</Name><SourceZones><Zone>DMZ</Zone></SourceZones><DestinationZones><Zone>Database</Zone></DestinationZones><SourceNetworks><Network>10.1.2.0/24</Network></SourceNetworks><DestinationNetworks><Network>10.1.3.0/24</Network></DestinationNetworks><Services><Service>MySQL</Service></Services><Action>Accept</Action><LogTraffic>Enable</LogTraffic></FirewallRule></Set></Request>"
}
```

### 11. OPNsense (REST API)

```bash
# Create alias for source
curl -X POST -u "<key>:<secret>" \
  "https://<opnsense>/api/firewall/alias/addItem" \
  -d '{"alias":{"name":"DMZ_WebServers","type":"network","content":"10.1.2.0/24","description":"DMZ web server subnet"}}'

# Create alias for destination
curl -X POST -u "<key>:<secret>" \
  "https://<opnsense>/api/firewall/alias/addItem" \
  -d '{"alias":{"name":"DB_Servers","type":"network","content":"10.1.3.0/24","description":"Database server subnet"}}'

# Create firewall filter rule
curl -X POST -u "<key>:<secret>" \
  "https://<opnsense>/api/firewall/filter/addRule" \
  -d '{"rule":{"enabled":"1","action":"pass","interface":"dmz","direction":"in","ipprotocol":"inet","protocol":"TCP","source_net":"DMZ_WebServers","destination_net":"DB_Servers","destination_port":"3306","description":"Allow DMZ web servers to MySQL","log":"1"}}'

# Apply changes
curl -X POST -u "<key>:<secret>" \
  "https://<opnsense>/api/firewall/filter/apply"
```

### 12. pfSense (easyrule / config.xml)

```bash
# Quick rule via easyrule
easyrule pass dmz tcp 10.1.2.0/24 10.1.3.0/24 3306

# config.xml rule structure (for reference)
# Add to <filter> section:
```

```xml
<rule>
  <type>pass</type>
  <interface>opt1</interface> <!-- DMZ interface -->
  <ipprotocol>inet</ipprotocol>
  <protocol>tcp</protocol>
  <source>
    <address>10.1.2.0/24</address>
  </source>
  <destination>
    <address>10.1.3.0/24</address>
    <port>3306</port>
  </destination>
  <descr>Allow DMZ web servers to MySQL</descr>
  <log/>
</rule>
```

```bash
# After config.xml edit, reload filter rules
pfctl -f /tmp/rules.debug   # or via GUI: apply changes
/etc/rc.filter_configure
```

### 13. VyOS (set commands)

VyOS firewall syntax differs between 1.3 LTS (legacy `set firewall name` / `set zone-policy zone`) and newer 1.4/1.5 nftables-backed trains. For 1.4/1.5, prefer the `set firewall ipv4 name ...` rule-set form and current zone firewall syntax; verify the exact commands in the official zone-based firewall documentation before applying: https://docs.vyos.io/en/latest/configuration/firewall/zone.html

```bash
# VyOS 1.4/1.5-style IPv4 firewall rule-set template — verify current syntax for your release.
set firewall ipv4 name DMZ-to-DB default-action drop

# Allow MySQL rule
set firewall ipv4 name DMZ-to-DB rule 10 action accept
set firewall ipv4 name DMZ-to-DB rule 10 description "Allow DMZ web servers to MySQL"
set firewall ipv4 name DMZ-to-DB rule 10 source address 10.1.2.0/24
set firewall ipv4 name DMZ-to-DB rule 10 destination address 10.1.3.0/24
set firewall ipv4 name DMZ-to-DB rule 10 destination port 3306
set firewall ipv4 name DMZ-to-DB rule 10 protocol tcp
set firewall ipv4 name DMZ-to-DB rule 10 log enable

# Attach the rule-set to the DMZ → DATABASE zone transition using the current zone syntax for your release.
# Example form to verify in docs before use:
set firewall zone DATABASE from DMZ firewall name DMZ-to-DB

# Apply
commit
save
```

> For VyOS 1.3 LTS, the older `set firewall name ...` and `set zone-policy zone ...` examples may still apply. Always match examples to the running VyOS release.

### 14. iptables / nftables

```bash
# iptables
# Create custom chain for zone transition
iptables -N DMZ_TO_DB
iptables -A FORWARD -i eth1 -o eth2 -j DMZ_TO_DB   # eth1=DMZ, eth2=DB

# Allow MySQL with logging
iptables -A DMZ_TO_DB -s 10.1.2.0/24 -d 10.1.3.0/24 -p tcp --dport 3306 \
  -m state --state NEW,ESTABLISHED -j LOG --log-prefix "[DMZ-to-DB-MySQL] "
iptables -A DMZ_TO_DB -s 10.1.2.0/24 -d 10.1.3.0/24 -p tcp --dport 3306 \
  -m state --state NEW,ESTABLISHED -j ACCEPT

# Default deny for chain
iptables -A DMZ_TO_DB -j DROP

# Save
iptables-save > /etc/iptables/rules.v4
```

```bash
# nftables equivalent
nft add table inet filter
nft add chain inet filter dmz_to_db '{ type filter hook forward priority 0; }'

nft add rule inet filter forward iifname "eth1" oifname "eth2" jump dmz_to_db

nft add rule inet filter dmz_to_db ip saddr 10.1.2.0/24 ip daddr 10.1.3.0/24 \
  tcp dport 3306 ct state new,established log prefix \"[DMZ-to-DB-MySQL] \" accept

nft add rule inet filter dmz_to_db drop

# Save
nft list ruleset > /etc/nftables.conf
```

---

## Best Practices for Generated Config

1. **Always include comments/descriptions** — every rule must have a human-readable description.
2. **Use named objects** — avoid hard-coded IPs in rules; define address and service objects.
3. **Log all rules** — enable session logging for allow rules and packet logging for deny rules.
4. **Include rollback commands** — provide the delete/remove commands alongside the add commands.
5. **Validate before applying** — recommend dry-run or test-policy-match tools per vendor.
6. **Commit atomically** — on platforms that support it (Junos, VyOS, PAN-OS), use commit/confirm with auto-rollback timers.

---
**Analysis only — verify against vendor documentation before applying.**
