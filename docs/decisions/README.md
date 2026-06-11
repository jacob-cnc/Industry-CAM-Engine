# Architecture and Operational Decisions

Use this directory for decisions that should survive individual sessions and
remain understandable months later.

File naming:

```text
ADR-001-short-title.md
ADR-002-short-title.md
```

Suggested format:

```markdown
# ADR-NNN: Title

## Status
Proposed | Accepted | Superseded

## Context

## Decision

## Consequences

## Evidence
```

Do not create an ADR for every small implementation detail. Use one when a
decision changes architecture, machine-operation policy, coordinate conventions,
deployment, validation, or cross-project reuse.

## Accepted Decisions

- `ADR-001-source-of-truth-and-verification.md` - shared and physical sources of
  truth, plus verification states
- `ADR-002-evidence-reference-and-change-discipline.md` - proportional reference
  review, evidence handling, and reversible change discipline
