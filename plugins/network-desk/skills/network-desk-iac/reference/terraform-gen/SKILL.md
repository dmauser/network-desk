# Skill: Terraform Configuration Generation

## Purpose

Generate production-ready Terraform configurations for networking infrastructure across Azure (azurerm), AWS (aws), and GCP (google) providers. Provides modular, parameterized configurations following HashiCorp and provider best practices.

---

## Core Conventions

### Provider Versions

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
```

> Pin providers to the current major version verified in the Terraform Registry and tested by your organization. The AWS `~> 6.0` and Google `~> 7.0` examples reflect current major-version guidance; review provider upgrade guides before adopting them.

### File Structure Convention

```
terraform/
├── main.tf              // Root module, provider config, module calls
├── variables.tf         // Input variables
├── outputs.tf           // Output values
├── terraform.tfvars     // Default variable values (not secrets)
├── backend.tf           // Remote state configuration
├── versions.tf          // Provider version constraints
├── locals.tf            // Computed local values
├── environments/
│   ├── dev.tfvars
│   ├── staging.tfvars
│   └── prod.tfvars
└── modules/
    ├── vnet/
    ├── firewall/
    ├── vpn-gateway/
    └── private-endpoint/
```

### Naming Convention

```hcl
locals {
  prefix      = "${var.organization}-${var.environment}-${var.region_code}"
  name_suffix = "${var.environment}-${var.region_code}"

  common_tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = var.project_name
    Owner       = var.owner
  }
}
```

---

## Azure Networking Templates (azurerm)

### 1. Hub VNet with Subnets

```hcl
resource "azurerm_virtual_network" "hub" {
  name                = "${local.prefix}-vnet-hub"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  address_space       = [var.hub_address_space]
  tags                = local.common_tags
}

resource "azurerm_subnet" "hub_subnets" {
  for_each = { for s in var.hub_subnets : s.name => s }

  name                 = each.value.name
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [each.value.prefix]

  dynamic "delegation" {
    for_each = lookup(each.value, "delegation", null) != null ? [each.value.delegation] : []
    content {
      name = delegation.value.name
      service_delegation {
        name    = delegation.value.service
        actions = delegation.value.actions
      }
    }
  }
}

variable "hub_subnets" {
  type = list(object({
    name   = string
    prefix = string
    delegation = optional(object({
      name    = string
      service = string
      actions = list(string)
    }))
  }))
  default = [
    { name = "AzureFirewallSubnet", prefix = "10.0.1.0/26" },
    { name = "GatewaySubnet", prefix = "10.0.255.0/27" },
    { name = "AzureBastionSubnet", prefix = "10.0.2.0/26" },
    { name = "snet-shared", prefix = "10.0.10.0/24" },
  ]
}
```

### 2. Spoke VNet with Peering

```hcl
resource "azurerm_virtual_network" "spoke" {
  for_each = { for s in var.spokes : s.name => s }

  name                = "${local.prefix}-vnet-${each.key}"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  address_space       = [each.value.address_space]
  tags                = local.common_tags
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  for_each = { for s in var.spokes : s.name => s }

  name                      = "peer-to-hub"
  resource_group_name       = azurerm_resource_group.network.name
  virtual_network_name      = azurerm_virtual_network.spoke[each.key].name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
  allow_forwarded_traffic   = true
  use_remote_gateways       = var.deploy_vpn_gateway
}

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  for_each = { for s in var.spokes : s.name => s }

  name                      = "peer-to-${each.key}"
  resource_group_name       = azurerm_resource_group.network.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.spoke[each.key].id
  allow_gateway_transit     = var.deploy_vpn_gateway
}
```

### 3. Azure Firewall

```hcl
resource "azurerm_firewall_policy" "main" {
  name                = "${local.prefix}-fwpol"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  sku                 = var.firewall_sku
  threat_intelligence_mode = "Alert"
  tags                = local.common_tags

  dns {
    proxy_enabled = true
  }
}

resource "azurerm_public_ip" "firewall" {
  name                = "${local.prefix}-pip-fw"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

resource "azurerm_firewall" "main" {
  name                = "${local.prefix}-fw"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  sku_name            = "AZFW_VNet"
  sku_tier            = var.firewall_sku
  firewall_policy_id  = azurerm_firewall_policy.main.id
  tags                = local.common_tags

  ip_configuration {
    name                 = "fw-ipconfig"
    subnet_id            = azurerm_subnet.hub_subnets["AzureFirewallSubnet"].id
    public_ip_address_id = azurerm_public_ip.firewall.id
  }
}

output "firewall_private_ip" {
  value = azurerm_firewall.main.ip_configuration[0].private_ip_address
}
```

### 4. NSG with Dynamic Rules

```hcl
resource "azurerm_network_security_group" "main" {
  name                = "${local.prefix}-nsg-${var.subnet_purpose}"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  tags                = local.common_tags

  dynamic "security_rule" {
    for_each = var.nsg_rules
    content {
      name                       = security_rule.value.name
      priority                   = security_rule.value.priority
      direction                  = security_rule.value.direction
      access                     = security_rule.value.access
      protocol                   = security_rule.value.protocol
      source_port_range          = "*"
      source_address_prefix      = security_rule.value.source
      destination_port_range     = security_rule.value.destination_port
      destination_address_prefix = security_rule.value.destination
    }
  }
}
```

---

## AWS Networking Templates

### 1. VPC with Subnets

```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.common_tags, { Name = "${local.prefix}-vpc" })
}

resource "aws_subnet" "private" {
  for_each = { for s in var.private_subnets : s.name => s }

  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
  tags              = merge(local.common_tags, { Name = "${local.prefix}-${each.key}" })
}

resource "aws_subnet" "public" {
  for_each = { for s in var.public_subnets : s.name => s }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true
  tags                    = merge(local.common_tags, { Name = "${local.prefix}-${each.key}" })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.common_tags, { Name = "${local.prefix}-igw" })
}

resource "aws_nat_gateway" "main" {
  for_each = { for s in var.public_subnets : s.name => s if s.nat_gateway }

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  tags          = merge(local.common_tags, { Name = "${local.prefix}-natgw-${each.key}" })
}
```

### 2. Transit Gateway

```hcl
resource "aws_ec2_transit_gateway" "main" {
  description                     = "Central transit gateway for ${var.organization}"
  default_route_table_association = "disable"
  default_route_table_propagation = "disable"
  auto_accept_shared_attachments  = "enable"
  tags                            = merge(local.common_tags, { Name = "${local.prefix}-tgw" })
}

resource "aws_ec2_transit_gateway_vpc_attachment" "spokes" {
  for_each = var.spoke_vpcs

  subnet_ids         = each.value.subnet_ids
  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpc_id             = each.value.vpc_id
  tags               = merge(local.common_tags, { Name = "${local.prefix}-tgw-attach-${each.key}" })
}

resource "aws_ec2_transit_gateway_route_table" "shared" {
  transit_gateway_id = aws_ec2_transit_gateway.main.id
  tags               = merge(local.common_tags, { Name = "${local.prefix}-tgw-rt-shared" })
}
```

### 3. Security Groups

```hcl
resource "aws_security_group" "main" {
  name_prefix = "${local.prefix}-sg-${var.purpose}-"
  vpc_id      = aws_vpc.main.id
  description = var.sg_description
  tags        = merge(local.common_tags, { Name = "${local.prefix}-sg-${var.purpose}" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "rules" {
  for_each = { for r in var.ingress_rules : r.name => r }

  security_group_id = aws_security_group.main.id
  description       = each.value.description
  from_port         = each.value.from_port
  to_port           = each.value.to_port
  ip_protocol       = each.value.protocol
  cidr_ipv4         = each.value.cidr
  tags              = { Name = each.key }
}

resource "aws_vpc_security_group_egress_rule" "allow_all" {
  security_group_id = aws_security_group.main.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
```

---

## GCP Networking Templates

### 1. VPC with Subnets

```hcl
resource "google_compute_network" "main" {
  name                    = "${local.prefix}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
  project                 = var.project_id
}

resource "google_compute_subnetwork" "subnets" {
  for_each = { for s in var.subnets : s.name => s }

  name                     = "${local.prefix}-subnet-${each.key}"
  ip_cidr_range            = each.value.cidr
  region                   = each.value.region
  network                  = google_compute_network.main.id
  private_ip_google_access = true
  project                  = var.project_id

  dynamic "secondary_ip_range" {
    for_each = lookup(each.value, "secondary_ranges", [])
    content {
      range_name    = secondary_ip_range.value.name
      ip_cidr_range = secondary_ip_range.value.cidr
    }
  }
}

resource "google_compute_router" "main" {
  name    = "${local.prefix}-router"
  region  = var.primary_region
  network = google_compute_network.main.id
  project = var.project_id

  bgp {
    asn = var.bgp_asn
  }
}

resource "google_compute_router_nat" "main" {
  name                               = "${local.prefix}-nat"
  router                             = google_compute_router.main.name
  region                             = var.primary_region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  project                            = var.project_id
}
```

### 2. Firewall Rules

```hcl
resource "google_compute_firewall" "rules" {
  for_each = { for r in var.firewall_rules : r.name => r }

  name        = "${local.prefix}-fw-${each.key}"
  network     = google_compute_network.main.name
  project     = var.project_id
  description = each.value.description
  direction   = each.value.direction
  priority    = each.value.priority

  dynamic "allow" {
    for_each = each.value.action == "allow" ? each.value.rules : []
    content {
      protocol = allow.value.protocol
      ports    = lookup(allow.value, "ports", null)
    }
  }

  dynamic "deny" {
    for_each = each.value.action == "deny" ? each.value.rules : []
    content {
      protocol = deny.value.protocol
      ports    = lookup(deny.value, "ports", null)
    }
  }

  source_ranges = lookup(each.value, "source_ranges", null)
  target_tags   = lookup(each.value, "target_tags", null)
}
```

---

## Remote State Configuration

### Azure Backend

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate"
    container_name       = "tfstate"
    key                  = "networking/prod.terraform.tfstate"
  }
}
```

### AWS Backend

```hcl
terraform {
  backend "s3" {
    bucket         = "my-org-terraform-state"
    key            = "networking/prod/terraform.tfstate"
    region         = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
```

Use S3 native lock files for state locking. DynamoDB state locking is legacy; keep it only for older Terraform estates that have not migrated.

### GCP Backend

```hcl
terraform {
  backend "gcs" {
    bucket = "my-org-terraform-state"
    prefix = "networking/prod"
  }
}
```

---

## Validation Commands

```bash
# Format code
terraform fmt -recursive

# Validate configuration
terraform validate

# Plan changes (always review before apply)
terraform plan -var-file=environments/prod.tfvars -out=tfplan

# Apply (with auto-approve only in CI/CD with proper guards)
terraform apply tfplan

# Destroy (use with caution)
terraform plan -destroy -var-file=environments/prod.tfvars -out=destroyplan
```

**Analysis only — verify against vendor documentation before applying.**
