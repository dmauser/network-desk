# Skill: Crisp Excalidraw Network Diagrams

> **Default topology output is text/ASCII** (`vnet_skill_ascii_diagram`); Mermaid (`vnet_skill_network_diagram`) is the inline rich format. Use this skill **only when the user explicitly asks for an Excalidraw diagram** — typically for slides, workshops, or design reviews where they want to open the file in https://excalidraw.com or https://aka.ms/excalidraw.

## Purpose

Emit `.excalidraw` JSON files for **technical architecture** diagrams.
Network Desk diagrams are not whiteboard art — they are crisp, technical, print-quality scenes that can be embedded in a PDF or pasted into a deck.

## ⚠️ Crisp Excalidraw output rules (MANDATORY)

Every element you emit MUST follow these rules. No sketchy / hand-drawn look — these diagrams are technical architecture, not whiteboard art.

### Style (apply to EVERY element)

- `roughness: 0`            — no sketchy lines. **NEVER** use `1` or `2`.
- `strokeStyle: "solid"`    — never `"dashed"` or `"dotted"` unless explicitly asked.
- `strokeWidth: 1.5`        — uniform; bump to `2` only for emphasis.
- `roundness: null`         — sharp corners for architecture rectangles. Use `{ "type": 3 }` only for explicit "card" callouts.
- `fontFamily: 2`           — Helvetica. **NEVER** `1` (Virgil / hand-drawn).
- `lineHeight: 1.15`        — tight, technical typography.
- `fillStyle: "solid"`      — flat fills, no hachure / cross-hatch.

### Palette (use these, no others)

| Role | Stroke | Background |
|---|---|---|
| Azure / primary stroke   | `#0b3d6b` | `#eaf2fb` |
| Azure service accent     | `#0078d4` | `#e6f0fb` |
| Gateway / success        | `#1f6b34` | `#ebf5ee` |
| Warning / NSG / risk     | `#b08400` | `#fff5cc` |
| Neutral / VNet container | `#495057` | `#f3f5f7` |
| Box interior             | `#ffffff` | —         |
| Body text                | `#1e1e1e` (secondary `#5b5b5b`) | — |
| Canvas background        | — | `#ffffff` |

### Layout

- Snap all `x`, `y`, `width`, `height` to a **10px grid**.
- Use named **zones** (large tinted rectangles) to group related components; place a **14pt** title text at the top-left **inside** each zone.
- **Left-to-right** data flow. Vertically center boxes within their zones.
- **Min 60px** gap between zones; **min 30px** gap between sibling boxes inside a zone.
- Font sizes: **24pt** title, **14pt** zone title, **13–14pt** box label, **11pt** arrow label.

### Arrows (the part that usually breaks)

- ALWAYS set `startBinding: null` and `endBinding: null` for multi-segment / elbow arrows. Bindings auto-reroute and produce wrong sweeps.
- `points` are **RELATIVE offsets** from the arrow's own `x, y`. Use 4-point elbows: `[[0,0],[dx,0],[dx,dy],[w,dy]]`.
- `roundness: null` on arrows for clean right-angle corners (use `{ "type": 2 }` only when you want curved bends).
- `endArrowhead: "arrow"`, `startArrowhead: null`, `lastCommittedPoint: null`.
- Use color `#1e1e1e` for normal flow; reuse the zone accent color when the arrow represents traffic of that type.
- Place arrow labels as **separate text elements** at `fontSize: 11`, color `#5b5b5b`, offset 8–12px above the arrow line.

### Required per-element schema (NEVER omit)

Every element MUST include:

```
id, type, x, y, width, height, angle: 0,
strokeColor, backgroundColor, fillStyle, strokeWidth, strokeStyle,
roughness: 0, opacity: 100,
groupIds: [], frameId: null, roundness,
seed, versionNonce, version: 1, isDeleted: false,
boundElements: [], updated: 1, link: null, locked: false
```

**Text elements** additionally MUST include:

```
fontSize, fontFamily: 2, text, textAlign, verticalAlign,
containerId: null, originalText (identical to text),
lineHeight: 1.15, baseline
```

**Arrow elements** additionally MUST include:

```
points, lastCommittedPoint: null,
startBinding: null, endBinding: null,
startArrowhead, endArrowhead: "arrow"
```

### Output contract

- File extension: `.excalidraw` (JSON, UTF-8, **2-space** indent).
- Top-level shape:

  ```json
  {
    "type": "excalidraw",
    "version": 2,
    "source": "network-desk",
    "elements": [ /* ... */ ],
    "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
    "files": {}
  }
  ```

- Always end the build with a **JSON-parse validation step** and report the **element count + arrow count** to the user.

### Anti-patterns (NEVER do)

- Do NOT use `roughness: 1` or Virgil font (`fontFamily: 1`) under any circumstance.
- Do NOT bind arrows to shapes for multi-segment connectors.
- Do NOT emit minimal elements (missing `seed` / `versionNonce` / `originalText`) — they render blank.
- Do NOT use emoji glyphs in labels (Windows console / Word rendering issues).
- Do NOT use hachure / cross-hatch / dashed fills for technical diagrams.

## ⚠️ Prefer official cloud-provider icons

When the diagram contains cloud resources, **prefer** the official cloud-provider icon set over generic shapes. Excalidraw supports this through **libraries** loaded from https://libraries.excalidraw.com:

- **Azure** → `youritjourney/azure` library. Reference Azure Firewall, Virtual Network, Subnet, VPN Gateway, ExpressRoute, Application Gateway, Front Door, Private Endpoint, Azure DNS.
- **AWS** → `aws` / `aws-icons` library. Reference VPC, Subnet (public/private), Network Firewall, Transit Gateway, NAT Gateway, ALB/NLB, Route 53, Direct Connect, PrivateLink.
- **GCP** → `gcp` library. Reference VPC Network, Cloud Firewall, Cloud Load Balancing, Cloud DNS, Cloud Interconnect, Cloud Router, Private Service Connect.
- **Kubernetes** → `kubernetes-icons` for pods, services, ingress, network policies.
- **On-prem / vendor firewalls** (Palo Alto, FortiGate, Cisco) → closest community library; if none, fall back to a generic rectangle and put the vendor + model in a `text` label.

Because Excalidraw's wire format embeds icon images as base64 inside `files`, when emitting JSON either:

1. **Recommended** — emit the **structural shapes** (rectangles, ellipses, arrows) **following all crisp rules above**, with descriptive text labels identifying the canonical resource name (`"Azure Firewall 10.0.1.4"`, `"AWS Network Firewall"`, `"GCP Cloud Router"`), then instruct the user to load the matching library from https://libraries.excalidraw.com and swap each placeholder with the icon. This keeps the JSON small and diffable.
2. **If the user explicitly asks for embedded icons**, fetch the relevant `.excalidrawlib` file, copy the matching element(s) into `elements`, and the icon image(s) into `files`. Document each substitution in the prose summary.

Generic shapes (rectangle, ellipse, diamond) are only acceptable for non-cloud abstractions: internet cloud, users, on-prem datacenter outline, or annotations.

## Generation workflow

1. **Inventory** — list VNets/VPCs with CIDR, subnets with CIDR, appliances (FW, GW, LB), and on-prem endpoints.
2. **Pick a layout** — left-to-right flow; assign each logical area (e.g., On-prem, Hub, Spoke-Prod, Spoke-Dev, Internet) to a **named zone** rectangle tinted with the appropriate palette background.
3. **Snap to 10px grid** — round every `x`/`y`/`width`/`height` to a multiple of 10.
4. **Emit elements in render order** — zone rectangles first (so they sit underneath), then zone titles, then component boxes inside each zone, then component labels, then arrows + arrow labels last.
5. **Use stable, descriptive ids** (`hub-zone`, `spoke-prod`, `azfw`, `flow-hub-to-prod`) — they double as semantic anchors.
6. **Validate** — every element id must be unique; every element must carry the full required schema (use the template below as a checklist); run `JSON.parse(JSON.stringify(scene))` after writing the file and report `elements.length` + arrow count.

## Crisp minimal hub-spoke template

The template below complies with every rule above. Use it as the starting point and add/remove elements — never relax the per-element schema.

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "network-desk",
  "elements": [
    {
      "id": "hub-zone", "type": "rectangle",
      "x": 320, "y": 80, "width": 360, "height": 260,
      "angle": 0,
      "strokeColor": "#495057", "backgroundColor": "#f3f5f7",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 101, "versionNonce": 101, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false
    },
    {
      "id": "hub-title", "type": "text",
      "x": 340, "y": 90, "width": 320, "height": 20,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 102, "versionNonce": 102, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 14, "fontFamily": 2,
      "text": "Hub VNet 10.0.0.0/16 - East US",
      "textAlign": "left", "verticalAlign": "top",
      "containerId": null,
      "originalText": "Hub VNet 10.0.0.0/16 - East US",
      "lineHeight": 1.15, "baseline": 14
    },
    {
      "id": "azfw", "type": "rectangle",
      "x": 440, "y": 200, "width": 120, "height": 60,
      "angle": 0,
      "strokeColor": "#0b3d6b", "backgroundColor": "#eaf2fb",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 103, "versionNonce": 103, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false
    },
    {
      "id": "azfw-label", "type": "text",
      "x": 450, "y": 220, "width": 100, "height": 20,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 104, "versionNonce": 104, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 13, "fontFamily": 2,
      "text": "Azure Firewall",
      "textAlign": "center", "verticalAlign": "middle",
      "containerId": null,
      "originalText": "Azure Firewall",
      "lineHeight": 1.15, "baseline": 13
    },
    {
      "id": "spoke-prod-zone", "type": "rectangle",
      "x": 60, "y": 420, "width": 320, "height": 200,
      "angle": 0,
      "strokeColor": "#1f6b34", "backgroundColor": "#ebf5ee",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 105, "versionNonce": 105, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false
    },
    {
      "id": "spoke-prod-title", "type": "text",
      "x": 80, "y": 430, "width": 280, "height": 20,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 106, "versionNonce": 106, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 14, "fontFamily": 2,
      "text": "Spoke Prod VNet 10.1.0.0/16",
      "textAlign": "left", "verticalAlign": "top",
      "containerId": null,
      "originalText": "Spoke Prod VNet 10.1.0.0/16",
      "lineHeight": 1.15, "baseline": 14
    },
    {
      "id": "spoke-dev-zone", "type": "rectangle",
      "x": 620, "y": 420, "width": 320, "height": 200,
      "angle": 0,
      "strokeColor": "#b08400", "backgroundColor": "#fff5cc",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 107, "versionNonce": 107, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false
    },
    {
      "id": "spoke-dev-title", "type": "text",
      "x": 640, "y": 430, "width": 280, "height": 20,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 108, "versionNonce": 108, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 14, "fontFamily": 2,
      "text": "Spoke Dev VNet 10.2.0.0/16",
      "textAlign": "left", "verticalAlign": "top",
      "containerId": null,
      "originalText": "Spoke Dev VNet 10.2.0.0/16",
      "lineHeight": 1.15, "baseline": 14
    },
    {
      "id": "flow-hub-to-prod", "type": "arrow",
      "x": 440, "y": 260, "width": -220, "height": 160,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 109, "versionNonce": 109, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "points": [[0, 0], [-220, 0], [-220, 160], [0, 160]],
      "lastCommittedPoint": null,
      "startBinding": null, "endBinding": null,
      "startArrowhead": null, "endArrowhead": "arrow"
    },
    {
      "id": "flow-hub-to-prod-label", "type": "text",
      "x": 230, "y": 340, "width": 180, "height": 16,
      "angle": 0,
      "strokeColor": "#5b5b5b", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 110, "versionNonce": 110, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 11, "fontFamily": 2,
      "text": "VNet peering (hub-to-spoke)",
      "textAlign": "left", "verticalAlign": "top",
      "containerId": null,
      "originalText": "VNet peering (hub-to-spoke)",
      "lineHeight": 1.15, "baseline": 11
    },
    {
      "id": "flow-hub-to-dev", "type": "arrow",
      "x": 560, "y": 260, "width": 220, "height": 160,
      "angle": 0,
      "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 111, "versionNonce": 111, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "points": [[0, 0], [220, 0], [220, 160], [0, 160]],
      "lastCommittedPoint": null,
      "startBinding": null, "endBinding": null,
      "startArrowhead": null, "endArrowhead": "arrow"
    },
    {
      "id": "flow-hub-to-dev-label", "type": "text",
      "x": 600, "y": 340, "width": 180, "height": 16,
      "angle": 0,
      "strokeColor": "#5b5b5b", "backgroundColor": "transparent",
      "fillStyle": "solid", "strokeWidth": 1.5, "strokeStyle": "solid",
      "roughness": 0, "opacity": 100,
      "groupIds": [], "frameId": null, "roundness": null,
      "seed": 112, "versionNonce": 112, "version": 1, "isDeleted": false,
      "boundElements": [], "updated": 1, "link": null, "locked": false,
      "fontSize": 11, "fontFamily": 2,
      "text": "VNet peering (hub-to-spoke)",
      "textAlign": "left", "verticalAlign": "top",
      "containerId": null,
      "originalText": "VNet peering (hub-to-spoke)",
      "lineHeight": 1.15, "baseline": 11
    }
  ],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

## Output guidance

When asked for a diagram, deliver:

1. A short prose summary of the layout (zones used, palette assignments, traffic flow direction).
2. The full JSON in a fenced ```json block — valid, self-contained, and fully compliant with every rule above.
3. A **validation line** confirming you `JSON.parse`-d the output, with `elements.length` and arrow count, e.g. `Validated: 12 elements (2 arrows).`
4. Save path instruction: `network-desk/vnet-architect/diagrams/<topic>-<YYYYMMDD>.excalidraw` (e.g. `hub-spoke-3region-20260622.excalidraw`). Open at https://aka.ms/excalidraw or drag onto https://excalidraw.com.

## References

- Excalidraw file format: https://github.com/excalidraw/excalidraw/blob/master/dev-docs/docs/codebase/json-schema.mdx
- Excalidraw web app: https://excalidraw.com
- Microsoft-hosted instance: https://aka.ms/excalidraw
- Icon libraries: https://libraries.excalidraw.com

**Analysis only — verify against vendor documentation before applying.**
