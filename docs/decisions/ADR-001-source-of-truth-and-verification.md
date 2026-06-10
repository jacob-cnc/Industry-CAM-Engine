# ADR-001: Source of Truth and Verification States

## Status

Accepted

## Context

The project is developed across multiple computers and by multiple human and AI
collaborators. The physical lathe can also accumulate machine-local tuning,
offsets, and observations that are not automatically represented by a Git commit.
Without explicit rules, a checked-in value, a session-note hypothesis, or an old
deployment can be mistaken for the current verified machine state.

## Decision

1. GitHub `main` is the shared source of truth for code and durable documentation.
2. The physical lathe is the source of truth for measured physical behavior.
3. Checked-in code and configuration are not considered machine-verified merely
   because they are on `main`.
4. Machine-local changes must be committed or documented before being treated as
   durable project knowledge.
5. Motion-affecting and machine-control work uses separate verification labels:
   - **Software-verified:** Confirmed by automated, offline, ground-truth, or
     round-trip checks.
   - **Machine-verified:** Confirmed by a recorded repeatable test on the physical
     machine.
6. Conflicting documents must be reconciled explicitly. Newer measured evidence
   and checked-in active configuration take precedence over stale descriptive
   text, but the conflict must be recorded and corrected.

## Consequences

- Contributors can reason about confidence without overstating it.
- Machine commissioning remains a distinct required activity.
- Handoffs and releases require slightly more documentation.
- Known-good machine deployments can be identified with Git tags and associated
  commissioning notes.

## Evidence

The existing session notes show several cases where wiring assumptions, encoder
mapping, PID values, and feature status evolved faster than descriptive
documentation. This decision formalizes the successful dated-session-note
  practice and adds a concise shared state layer.
