# Skill: Report Structure & Quality Bar

## Purpose

Define the standard skeleton and quality checklist for every network-desk deliverable, so reports are consistent, professional, and ready to render to HTML/PDF/DOCX/XLSX.

This skill governs **structure and quality**. The four renderer skills (`html-report`, `pdf-report`, `docx-report`, `xlsx-workbook`) govern **format conversion**.

## Standard report skeleton (Markdown)

Author the report as Markdown first — it is the source of truth that every renderer consumes.

```markdown
# <Specialist> — <Topic>
<!-- e.g. "Firewall Engineering — Azure Firewall Rule Audit" -->

## Executive Summary
2–5 sentences a non-expert can act on: what was analyzed, the headline finding,
and the single most important recommendation. No jargon, no preamble.

## Scope & Assumptions
- What is in / out of scope
- Environment (cloud, region, subscription/account)
- Assumptions and the date of analysis (vendor limits/pricing change)

## Findings
Use a table for anything enumerable (rules, costs, gaps, risks). Rank by severity.

| # | Finding | Severity | Evidence | Impact |
|---|---------|----------|----------|--------|
| 1 | ...     | High     | ...      | ...    |

## Architecture / Topology
Embed at least one Mermaid diagram for any design or topology. (Use the
`cn_vnet` `network-diagram` skill to generate it.) Offer Excalidraw/draw.io on request.

## Recommendations
Numbered, prioritized, each with the concrete next step and the owner/effort.

## Appendix / References
- Vendor documentation links (with the product name)
- Raw data, calculations, or command output

> Analysis only — verify against vendor documentation before applying.
```

## Quality checklist (apply before rendering)

- [ ] **Executive summary leads** — reader gets the answer in the first paragraph.
- [ ] **Every number is sourced** — limits/quotas/prices cite a vendor doc and a date, or are labeled "illustrative — verify current values".
- [ ] **Findings are in a table**, ranked by severity, with evidence and impact columns.
- [ ] **At least one diagram** for any architecture/topology.
- [ ] **Recommendations are actionable** — numbered, prioritized, with next steps.
- [ ] **Headings are hierarchical** (`#` → `##` → `###`) — the DOCX/PDF TOC is built from them.
- [ ] **No secrets** — redact keys, tokens, connection strings, public IPs of real systems.
- [ ] **Footer present** — ends with the analysis-only line.

## Format selection — pick by purpose

| Format | Use when… | Renderer skill |
|--------|-----------|----------------|
| **Markdown** | Inline review, GitHub/PR, source of truth | (none — author directly) |
| **HTML** | Quick shareable, self-contained, opens in any browser | `html-report` |
| **PDF** | Stakeholder/exec hand-off, print, fixed layout | `pdf-report` |
| **DOCX** | Editable deliverable, corporate templates, tracked changes | `docx-report` |
| **XLSX** | Cost models, capacity plans, anything with **editable formulas** | `xlsx-workbook` |

When the user says "report" without a format, default to **Markdown + HTML** and offer PDF/DOCX/XLSX.

## Output location

Save the Markdown source and every rendered artifact under:

```
network-desk/<specialist>/reports/<kebab-topic>-<YYYYMMDD>.<ext>
```

`<specialist>` is the owning domain specialist's directory name (e.g. `firewall-engineer`, `pricing-analyst`, `vnet-architect`). Keep the `.md` source next to the rendered file so it can be regenerated.

## References

- Keep a Changelog (structure inspiration): https://keepachangelog.com/
- Microsoft Azure architecture docs: https://learn.microsoft.com/azure/architecture/networking/

**Analysis only — verify against vendor documentation before applying.**
