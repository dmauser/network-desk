# NetOps evals

Scenario evals for the `netops` Azure SRE Agent plugin. Each fixture models a fault from the
NetOps labs and checks the whole read-only chain:

**injected fault → operator symptom → expected skill routing → expected finding**

| Source | Scenarios |
| --- | --- |
| [dmauser/azure-sre-netops](https://github.com/dmauser/azure-sre-netops) | SC-01..SC-08 |
| [dmauser/az-srenetops-microhack](https://github.com/dmauser/az-srenetops-microhack) | challenge scenarios (added with the matching skills) |

## Run

```bash
python evals/netops/run.py            # table, exit 1 on failure
python -m pytest -q evals/netops      # same scenarios under pytest (CI)
```

## Fixture format (`fixtures/*.json`)

| Key | Meaning |
| --- | --- |
| `id`, `title`, `source` | Scenario id, short name, lab repository |
| `injected_fault` | What the lab changes (never executed here) |
| `symptom` | What the operator tells the agent; routed with `plugins/netops/agents/routing.json` |
| `expected_skill` | Skill the investigator must pick first |
| `followup_skills` | Optional skills the investigator should chain to next (informational) |
| `input` or `input_ref` | Read-only evidence the skill would collect (inline, or a path relative to the repo root) |
| `expect.finding_prefixes` | Finding ids (prefix match) that must be present |
| `expect.absent_prefixes` | Finding ids that must not be present |
| `expect.top_severity` | Severity of the first (worst) finding |
| `expect.max_severity` | No finding may be worse than this (planned-change scenarios such as SC-08) |
| `expect.evidence_gap_contains` | Substrings that must appear in `evidence_gaps` |
| `expect.partial` | Expected `partial` flag |

The router mirrors `netops-investigator`: each skill scores the number of matching symptom
regexes, ties break by `order`, and no match falls back to `netops-routing-analyzer`.
