# ADR-002: Evidence, Reference, and Change Discipline

## Status

Accepted

## Context

The project combines machine-specific commissioning knowledge, external
technical references, and evolving software. Existing behavior may encode a
valuable discovery, but it may also be incomplete, accidental, or wrong.
External references can explain proven approaches, but they may target different
versions, machines, coordinate systems, or safety assumptions.

The team needs to retain hard-won knowledge without treating the current project
or any reference implementation as unquestionable. Investigation must improve
decisions without routinely stalling focused work.

## Decision

### Evidence hierarchy

Use the strongest applicable evidence available:

1. Repeatable measurement on the physical machine
2. Current active machine configuration and observed runtime state
3. Official documentation or source matching the installed version
4. Project regression tests and vetted ground truth
5. Relevant external reference implementations
6. Engineering inference
7. Unverified assumption

This is a guide to confidence, not an automatic voting system. Conflicts must be
made explicit. A lower-ranked source may expose a defect in a higher-ranked
source, but the contradiction requires verification.

### Proportional reference review

Before a substantial design or change, identify the references relevant to the
decision and review them in proportion to risk and uncertainty:

- Software-only, familiar, reversible work needs a focused search.
- Motion-affecting, machine-control, unfamiliar, or hard-to-reverse work needs a
  deeper review of official sources, project history, and applicable references.
- Do not read unrelated reference trees merely to satisfy process.

### Existing behavior is evidence, not authority

When behavior appears surprising, check whether nearby tests, history, notes,
configuration, or references explain it. Time-box this investigation according
to risk. Preserve the reasoning when it is valuable.

Existing behavior receives no presumption of correctness. Contributors should
challenge it when evidence, simpler designs, or creative alternatives justify
doing so.

### References are advisory until applicability is established

For a borrowed design or technical conclusion, record when material:

- The reference, version, or retrieval date
- The behavior or principle being used
- Relevant assumptions that match this project
- Important mismatches or limitations
- Local verification performed

Reference source code is not automatically correct for the installed runtime or
this machine.

### Preserve momentum through reversibility

Prefer focused branches, small commits, tests, manifests, and rollback plans so
the team can explore ideas without losing known-good work. Investigation should
end when additional reading is unlikely to change the current decision or when a
targeted experiment can answer the question faster.

### Preserve important discoveries

When a decision is surprising, safety-relevant, or likely to be revisited,
preserve it in the smallest durable form that prevents repeated confusion:

- Regression test
- Dated session note
- Current-state or risk update
- ADR for durable cross-project policy

Do not create documentation for every incidental implementation choice.

## Consequences

- Contributors are expected to consult references, but not to defer progress
  indefinitely.
- Current code, machine observations, and external references can all be
  challenged.
- Version and applicability become visible parts of technical reasoning.
- Reversible experiments are preferred when evidence is incomplete.

## Evidence

Project history includes machine mappings, tuning values, coordinate
conventions, and geometry tolerances that changed as measurements improved. The
reference library also contains a LinuxCNC `2.10.0~pre1` source snapshot while
the documented machine runtime is LinuxCNC `2.9.6`, demonstrating why useful
reference material still requires an applicability check.
