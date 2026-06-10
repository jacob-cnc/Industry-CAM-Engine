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
