# Skill: draw.io Network Diagram Generation (alternative format)

> **Mermaid is the primary diagram format for this specialist** (see `vnet_skill_network_diagram`). Use draw.io only when the user explicitly asks for it — typically when they want polished, presentation-ready architecture diagrams with native cloud-provider stencils for export to PNG/SVG/PDF.

## Purpose

Generate `.drawio` XML diagrams from a network topology description. The output can be:

- Saved as `topology.drawio` and opened in https://app.diagrams.net (or the desktop / VS Code "Draw.io Integration" extension)
- Pasted via **Extras → Edit Diagram** in the draw.io editor
- Embedded in Confluence / SharePoint / GitHub README via the draw.io plugin or as exported PNG/SVG

Use this skill when the user wants a polished, presentation-ready architecture diagram using **native cloud provider stencils** (Azure, AWS, GCP icon sets are first-class in draw.io).

## ⚠️ Always prefer cloud-provider icons

When the diagram contains cloud resources, **always** use the official cloud-provider shape from the matching draw.io stencil library — never use generic rectangles for a service that has a vendor stencil. Match the provider to the resource:

- **Azure** resources → `shape=mxgraph.azure2.*` (current Azure icon set) — e.g. `mxgraph.azure2.firewalls`, `mxgraph.azure2.virtual_networks`, `mxgraph.azure2.subnets`, `mxgraph.azure2.application_gateways`, `mxgraph.azure2.dns_zones`, `mxgraph.azure2.virtual_network_gateways`, `mxgraph.azure2.private_endpoints`, `mxgraph.azure2.load_balancers`
- **AWS** resources → `shape=mxgraph.aws4.*` (AWS 2021 icon set) — e.g. `mxgraph.aws4.vpc`, `mxgraph.aws4.subnet_private`, `mxgraph.aws4.subnet_public`, `mxgraph.aws4.network_firewall`, `mxgraph.aws4.transit_gateway`, `mxgraph.aws4.application_load_balancer`, `mxgraph.aws4.route_53`, `mxgraph.aws4.direct_connect`, `mxgraph.aws4.privatelink`
- **GCP** resources → `shape=mxgraph.gcp2.*` — e.g. `mxgraph.gcp2.vpc_network`, `mxgraph.gcp2.cloud_firewall_rules`, `mxgraph.gcp2.cloud_load_balancing`, `mxgraph.gcp2.cloud_dns`, `mxgraph.gcp2.cloud_interconnect`, `mxgraph.gcp2.cloud_router`, `mxgraph.gcp2.private_service_connect`
- **Kubernetes** resources → `shape=mxgraph.kubernetes.icon;prIcon=*` (e.g. `prIcon=pod`, `prIcon=svc`, `prIcon=ing`, `prIcon=netpol`)
- **On-prem / vendor firewalls** (Palo Alto, FortiGate, Cisco, Check Point, Juniper) → use `mxgraph.cisco_safe.*` or generic stencils, and put the vendor + model in the label

Generic shapes (`rounded=1`, `ellipse`, `rhombus`) are only acceptable for non-cloud abstractions: internet cloud, users, on-prem datacenter outline, or annotations.

## Core Knowledge

### File format

A `.drawio` file is an XML document. Use the inline (un-compressed) form so it's human-readable and easy to diff:

```xml
<mxfile host="app.diagrams.net" type="device">
  <diagram id="net" name="Network">
    <mxGraphModel dx="1422" dy="757" grid="1" gridSize="10" guides="1" tooltips="1"
                  connect="1" arrows="1" fold="1" page="1" pageScale="1"
                  pageWidth="1169" pageHeight="826" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- shapes and edges go here, parent="1" -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Every shape is an `mxCell` with `vertex="1"`, a `style=` string (where the stencil reference lives), and a child `mxGeometry`. Edges set `edge="1"` with `source=` and `target=` referencing other cell ids.

### Style strings — the rule

The `style=` attribute determines the icon. Format:

```
shape=mxgraph.<library>.<stencil>;html=1;labelPosition=center;verticalLabelPosition=bottom;
align=center;verticalAlign=top;fillColor=<color>;strokeColor=<color>;
```

For Azure / AWS / GCP stencils, the official styling pattern is:

```
sketch=0;points=[[0,0,0],[0.5,0,0],[1,0,0],[1,0.5,0],[1,1,0],[0.5,1,0],[0,1,0],[0,0.5,0]];
outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#E7157B;strokeColor=#ffffff;
dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;
shape=mxgraph.azure2.firewalls;
```

(Brand colors: Azure pink-magenta `#0078D4` / `#E7157B`, AWS orange `#D86613` / `#232F3E`, GCP blue `#4285F4`.)

### Containers

Group resources by VNet/VPC using a container `mxCell` with `container=1;collapsible=0`. Children reference it via `parent="<container-id>"`. This lets the user drag a whole VNet as one unit and visually scope its contents.

```xml
<mxCell id="hub" value="Hub VNet (10.0.0.0/16) - East US"
        style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;
               verticalAlign=top;container=1;collapsible=0;"
        vertex="1" parent="1">
  <mxGeometry x="320" y="80" width="360" height="280" as="geometry"/>
</mxCell>
```

### Edges (connections)

| Connection | Edge style |
|------------|------------|
| VNet / VPC peering (bidirectional) | `endArrow=classic;startArrow=classic;html=1;` |
| Site-to-site VPN (encrypted tunnel) | `endArrow=classic;html=1;dashed=1;dashPattern=8 4;` |
| ExpressRoute / Direct Connect / Interconnect (private) | `endArrow=classic;html=1;strokeWidth=3;` |
| One-way traffic flow | `endArrow=classic;html=1;` |
| UDR / next hop | `endArrow=classic;html=1;dashed=1;` |

Always label the edge: `value="VNet Peering"`, `value="S2S VPN / IPsec"`, `value="ExpressRoute"`, `value="HTTPS 443"`, etc.

### Minimal hub-spoke template (Azure)

```xml
<mxfile host="app.diagrams.net" type="device">
  <diagram id="net" name="Hub-Spoke">
    <mxGraphModel dx="1422" dy="757" grid="1" gridSize="10" guides="1" tooltips="1"
                  connect="1" arrows="1" fold="1" page="1" pageScale="1"
                  pageWidth="1169" pageHeight="826" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>

        <!-- Hub VNet container -->
        <mxCell id="hub" value="Hub VNet (10.0.0.0/16) - East US"
                style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;verticalAlign=top;container=1;collapsible=0;"
                vertex="1" parent="1">
          <mxGeometry x="320" y="80" width="360" height="280" as="geometry"/>
        </mxCell>

        <!-- Azure Firewall (native stencil) -->
        <mxCell id="azfw" value="Azure Firewall&#10;10.0.1.4"
                style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;shape=mxgraph.azure2.firewalls;"
                vertex="1" parent="hub">
          <mxGeometry x="40" y="60" width="64" height="64" as="geometry"/>
        </mxCell>

        <!-- VPN Gateway (native stencil) -->
        <mxCell id="vpngw" value="VPN Gateway&#10;10.0.255.4"
                style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#0078D4;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;shape=mxgraph.azure2.virtual_network_gateways;"
                vertex="1" parent="hub">
          <mxGeometry x="160" y="60" width="64" height="64" as="geometry"/>
        </mxCell>

        <!-- Spoke-Prod container -->
        <mxCell id="spokeProd" value="Spoke-Prod (10.1.0.0/16)"
                style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;verticalAlign=top;container=1;collapsible=0;"
                vertex="1" parent="1">
          <mxGeometry x="60" y="420" width="300" height="200" as="geometry"/>
        </mxCell>
        <mxCell id="prodWeb" value="Web Subnet&#10;10.1.1.0/24"
                style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#0078D4;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;shape=mxgraph.azure2.subnets;"
                vertex="1" parent="spokeProd">
          <mxGeometry x="30" y="60" width="64" height="64" as="geometry"/>
        </mxCell>

        <!-- Spoke-Dev container -->
        <mxCell id="spokeDev" value="Spoke-Dev (10.2.0.0/16)"
                style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;verticalAlign=top;container=1;collapsible=0;"
                vertex="1" parent="1">
          <mxGeometry x="640" y="420" width="300" height="200" as="geometry"/>
        </mxCell>

        <!-- On-premises (generic, non-cloud) -->
        <mxCell id="onprem" value="On-Premises DC&#10;192.168.0.0/16"
                style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;dashed=1;"
                vertex="1" parent="1">
          <mxGeometry x="60" y="120" width="120" height="80" as="geometry"/>
        </mxCell>

        <!-- Peering edges -->
        <mxCell id="peer1" value="VNet Peering"
                style="endArrow=classic;startArrow=classic;html=1;" edge="1" parent="1" source="hub" target="spokeProd">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="peer2" value="VNet Peering"
                style="endArrow=classic;startArrow=classic;html=1;" edge="1" parent="1" source="hub" target="spokeDev">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="vpn" value="S2S VPN / IPsec"
                style="endArrow=classic;html=1;dashed=1;dashPattern=8 4;" edge="1" parent="1" source="vpngw" target="onprem">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### Generation workflow

1. **Inventory** — list VNets/VPCs with CIDR, subnets with CIDR, appliances (FW/GW/LB), gateways, on-prem endpoints.
2. **Pick stencil set** per resource based on cloud provider (`mxgraph.azure2`, `mxgraph.aws4`, `mxgraph.gcp2`). If you don't know the exact stencil name for a resource, use the closest match and put the canonical product name in the cell `value=` so it's still identifiable.
3. **Create containers first** (VNets / VPCs / regions) with `container=1`. Place all child resources via `parent="<container-id>"` and child-relative `mxGeometry`.
4. **Place icons** — 64×64 px for service icons is the visual norm; leave 80 px gutters; align in horizontal rows of related services.
5. **Wire edges** with `source=` / `target=` referencing cell ids; always set a descriptive `value=` (protocol, port, or relationship type).
6. **Validate** — every `source`/`target` and `parent` references an existing cell id; all ids are unique; XML is well-formed.

### Tips

- Set `pageWidth="1169" pageHeight="826"` (A4 landscape) for printable diagrams; bump to `pageWidth="1600"` for wide layouts.
- Use `&#10;` inside `value=` for line breaks within a label.
- For multi-region diagrams, create one container per region, then nest VNet containers inside.
- Need a stencil that doesn't exist? Fall back to `shape=mscae/<name>` (older Azure set), `mxgraph.cisco`, or a generic rounded rectangle, and put the full product name in the label.
- Recommend the user export to PNG/SVG via **File → Export As** for README embedding.

### Output guidance

When asked for a diagram, deliver:

1. A short prose summary of the layout and which stencil set was chosen.
2. The full XML in a fenced ```xml block, well-formed and self-contained.
3. Instructions: "Save under `network-desk/vnet-architect/diagrams/<topic>-<YYYYMMDD>.drawio` (e.g. `hub-spoke-3region-20260528.drawio`) and open at https://app.diagrams.net, or use **Extras → Edit Diagram** to paste it directly."

## References

- draw.io shape libraries: https://www.drawio.com/doc/faq/built-in-shape-libraries
- Azure stencils (`mxgraph.azure2`): https://www.drawio.com/blog/azure-diagrams
- AWS stencils (`mxgraph.aws4`): https://www.drawio.com/blog/aws-diagrams
- GCP stencils (`mxgraph.gcp2`): https://www.drawio.com/blog/google-cloud-platform
- File format reference: https://www.drawio.com/doc/faq/save-file-formats

**Analysis only — verify against vendor documentation before applying.**
