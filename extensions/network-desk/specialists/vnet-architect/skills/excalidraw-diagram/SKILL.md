# Skill: Excalidraw Network Diagram Generation (alternative format)

> **Mermaid is the primary diagram format for this specialist** (see `vnet_skill_network_diagram`). Use Excalidraw only when the user explicitly asks for it — typically for hand-drawn / whiteboard-style architecture diagrams for slides, workshops, or design reviews.

## Purpose

Generate Excalidraw scene JSON (`.excalidraw` files) from a network topology description. The output can be:

- Saved as `topology.excalidraw` and opened at https://excalidraw.com or https://aka.ms/excalidraw
- Pasted via **File → Open** or drag-and-drop into the Excalidraw web/desktop app
- Embedded in documentation alongside Mermaid for hand-drawn, presentation-friendly visuals

Use this skill when the user wants a sketchy / whiteboard-style architecture diagram instead of structured Mermaid.

## ⚠️ Always prefer cloud-provider icons

When the diagram contains cloud resources, **always** prefer the official cloud-provider icon set over generic shapes. Excalidraw supports this through **libraries** loaded from https://libraries.excalidraw.com:

- **Azure** → load `youritjourney/azure` library (search "Azure" on libraries.excalidraw.com). Reference shapes such as Azure Firewall, Virtual Network, Subnet, VPN Gateway, ExpressRoute, Application Gateway, Front Door, Private Endpoint, Azure DNS.
- **AWS** → load the `aws` / `aws-icons` library. Reference VPC, Subnet (public/private), Network Firewall, Transit Gateway, NAT Gateway, ALB/NLB, Route 53, Direct Connect, PrivateLink.
- **GCP** → load the `gcp` library. Reference VPC Network, Cloud Firewall, Cloud Load Balancing, Cloud DNS, Cloud Interconnect, Cloud Router, Private Service Connect.
- **Kubernetes** → load `kubernetes-icons` for pods, services, ingress, network policies.
- **On-prem / vendor firewalls** (Palo Alto, FortiGate, Cisco) → use the closest community library; if none, fall back to a generic shape and put the vendor + model in a `text` label.

Because Excalidraw's wire format embeds icon images as base64 inside `files`, when emitting the JSON either:

1. **Recommended** — emit the structural shapes (rectangles, ellipses, arrows) with **descriptive text labels** identifying the canonical resource name (`"Azure Firewall 10.0.1.4"`, `"AWS Network Firewall"`, `"GCP Cloud Router"`), then instruct the user to load the matching library from https://libraries.excalidraw.com and swap each placeholder with the icon. This keeps the JSON small and diffable.
2. **If the user explicitly asks for embedded icons**, fetch the relevant `.excalidrawlib` file, copy the matching element(s) into `elements`, and the icon image(s) into `files`. Document each substitution in the prose summary.

Generic shapes (rectangle, ellipse, diamond) are only acceptable for non-cloud abstractions: internet cloud, users, on-prem datacenter outline, or annotations.

## Core Knowledge

### File format

An Excalidraw scene is a JSON document with this top-level shape:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [ /* shapes, text, arrows */ ],
  "appState": { "viewBackgroundColor": "#ffffff", "gridSize": 20 },
  "files": {}
}
```

Every element needs: `id` (unique string), `type`, `x`, `y`, `width`, `height`, `angle: 0`, `strokeColor`, `backgroundColor`, `fillStyle`, `strokeWidth`, `strokeStyle`, `roughness`, `opacity: 100`, `groupIds: []`, `frameId: null`, `roundness`, `seed`, `version: 1`, `versionNonce`, `isDeleted: false`, `boundElements: null`, `updated`, `link: null`, `locked: false`.

### Standard component → shape map

| Network component | Excalidraw type | Style |
|-------------------|-----------------|-------|
| VNet / VPC (container) | `rectangle` (large, hachure fill) | `strokeColor: "#1971c2"`, `backgroundColor: "#a5d8ff"`, `fillStyle: "hachure"`, `roundness: { type: 3 }` |
| Subnet | `rectangle` | `strokeColor: "#2f9e44"`, `backgroundColor: "#b2f2bb"`, `fillStyle: "solid"` |
| Firewall / NVA | `diamond` | `strokeColor: "#e03131"`, `backgroundColor: "#ffc9c9"` |
| Gateway (VPN/ER) | `ellipse` | `strokeColor: "#5f3dc4"`, `backgroundColor: "#d0bfff"` |
| Load Balancer | rounded `rectangle` | `strokeColor: "#0c8599"`, `backgroundColor: "#99e9f2"` |
| Internet | `ellipse` | `strokeColor: "#495057"`, `backgroundColor: "#dee2e6"` |
| On-prem DC | dashed `rectangle` | `strokeStyle: "dashed"`, `strokeColor: "#5c3d00"` |
| Label / annotation | `text` | `fontFamily: 1` (hand-drawn), `fontSize: 20`, `textAlign: "center"` |
| Connection (peering, VPN, route) | `arrow` with `startBinding`/`endBinding` | thickness 2; `strokeStyle: "dashed"` for VPN |

### Layout conventions

1. **Hub-spoke**: hub container centered around `(400, 200)`; spokes radial at `(60,420)`, `(640,420)`.
2. **Multi-region**: split canvas vertically; left half region A, right half region B; global peering arrow crosses the divider.
3. **No true nesting**: subnets sit visually *inside* the VNet rectangle by coordinates, but every element is a top-level entry in `elements`. Use `groupIds: ["spoke-prod"]` to bundle them so they move together.
4. Budget ~400×260 per VNet container, ~120×80 per appliance, ~80 px gutter between containers.

### Minimal hub-spoke template

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [
    {
      "id": "hub-vnet", "type": "rectangle",
      "x": 320, "y": 80, "width": 360, "height": 260,
      "angle": 0, "strokeColor": "#1971c2", "backgroundColor": "#a5d8ff",
      "fillStyle": "hachure", "strokeWidth": 2, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": ["hub"], "frameId": null,
      "roundness": { "type": 3 }, "seed": 1, "version": 1, "versionNonce": 1,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false
    },
    {
      "id": "hub-label", "type": "text",
      "x": 360, "y": 90, "width": 280, "height": 25,
      "angle": 0, "strokeColor": "#1971c2", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": ["hub"], "frameId": null,
      "roundness": null, "seed": 2, "version": 1, "versionNonce": 2,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false,
      "text": "Hub VNet (10.0.0.0/16) - East US",
      "fontSize": 20, "fontFamily": 1, "textAlign": "center", "verticalAlign": "top",
      "baseline": 18, "containerId": null, "originalText": "Hub VNet (10.0.0.0/16) - East US"
    },
    {
      "id": "azfw", "type": "diamond",
      "x": 380, "y": 180, "width": 100, "height": 80,
      "angle": 0, "strokeColor": "#e03131", "backgroundColor": "#ffc9c9",
      "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": ["hub"], "frameId": null,
      "roundness": null, "seed": 3, "version": 1, "versionNonce": 3,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false
    },
    {
      "id": "spoke-prod", "type": "rectangle",
      "x": 60, "y": 420, "width": 300, "height": 200,
      "angle": 0, "strokeColor": "#2f9e44", "backgroundColor": "#b2f2bb",
      "fillStyle": "hachure", "strokeWidth": 2, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": ["spoke-prod"], "frameId": null,
      "roundness": { "type": 3 }, "seed": 4, "version": 1, "versionNonce": 4,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false
    },
    {
      "id": "spoke-dev", "type": "rectangle",
      "x": 640, "y": 420, "width": 300, "height": 200,
      "angle": 0, "strokeColor": "#f08c00", "backgroundColor": "#ffe8a1",
      "fillStyle": "hachure", "strokeWidth": 2, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": ["spoke-dev"], "frameId": null,
      "roundness": { "type": 3 }, "seed": 5, "version": 1, "versionNonce": 5,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false
    },
    {
      "id": "peer-prod", "type": "arrow",
      "x": 360, "y": 340, "width": -150, "height": 80,
      "angle": 0, "strokeColor": "#1971c2", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
      "roughness": 1, "opacity": 100, "groupIds": [], "frameId": null,
      "roundness": { "type": 2 }, "seed": 6, "version": 1, "versionNonce": 6,
      "isDeleted": false, "boundElements": null, "updated": 1, "link": null, "locked": false,
      "points": [[0, 0], [-150, 80]],
      "lastCommittedPoint": null,
      "startBinding": { "elementId": "hub-vnet", "focus": 0, "gap": 5 },
      "endBinding": { "elementId": "spoke-prod", "focus": 0, "gap": 5 },
      "startArrowhead": "arrow", "endArrowhead": "arrow"
    }
  ],
  "appState": { "viewBackgroundColor": "#ffffff", "gridSize": 20 },
  "files": {}
}
```

### Generation workflow

1. **Inventory**: list VNets/VPCs with CIDR, subnets with CIDR, appliances (FW, GW, LB), and on-prem endpoints.
2. **Pick a layout**: hub-spoke radial, multi-region split, or linear (single-VNet detail).
3. **Allocate coordinates**: containers first, then subnets and appliances by relative placement inside the container.
4. **Emit elements in render order**: containers (so they sit underneath), subnets, appliances, text labels, then arrows (wire arrows with `startBinding`/`endBinding` to element ids).
5. **Use stable, descriptive ids** (`hub-vnet`, `spoke-prod`, `azfw`, `peer-prod`) — they double as semantic anchors.
6. **Validate**: every arrow's `startBinding.elementId` and `endBinding.elementId` must exist in `elements`; all element ids must be unique.

### Tips

- Keep `roughness: 1` for the hand-drawn look; set `roughness: 0` for crisp lines.
- Use `groupIds` to bundle a subgraph (VNet + subnets + appliances) so Ctrl+drag moves them as one unit.
- For dashed/dotted connections (VPN tunnel), set `strokeStyle: "dashed"` on the arrow.
- Fonts are numeric: `1` = Virgil (hand-drawn), `2` = Helvetica, `3` = Cascadia.
- Coordinates can be negative; Excalidraw auto-frames on open.

### Output guidance

When asked for a diagram, deliver:

1. A short prose summary of the layout choices.
2. The full JSON in a fenced ```json block, valid and self-contained.
3. Instructions: "Save under `network-desk/vnet-architect/diagrams/<topic>-<YYYYMMDD>.excalidraw` (e.g. `hub-spoke-3region-20260528.excalidraw`) and open at https://aka.ms/excalidraw, or drag the file onto excalidraw.com."

## References

- Excalidraw file format: https://github.com/excalidraw/excalidraw/blob/master/dev-docs/docs/codebase/json-schema.mdx
- Excalidraw web app: https://excalidraw.com
- Microsoft-hosted instance: https://aka.ms/excalidraw

**Analysis only — verify against vendor documentation before applying.**
