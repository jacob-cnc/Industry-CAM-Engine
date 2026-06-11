# Linux Claude Prompt: Close Machine Reference Gaps

Use this prompt during the next session on the Linux lathe PC. This task remains
queued even if other agents complete unrelated sessions first.

---

You are working on the Linux lathe PC for the Industry CAM Engine project.

## Required Starting Steps

1. Pull the latest `main`.
2. Read:
   - `AGENTS.md`
   - `docs/CURRENT_STATE.md`
   - `docs/RISK_REGISTER.md`
   - `docs/decisions/ADR-002-evidence-reference-and-change-discipline.md`
   - `reference/INDEX.md`
   - Newest relevant files in `session-notes/`
3. Confirm the worktree and active branch before making changes.
4. Create a focused branch such as `claude/linux-reference-gap-acquisition`.

## Goal

Close as many high-priority machine-reference gaps from `reference/INDEX.md` as
can be established on the Linux PC and physical lathe. Preserve exact evidence,
provenance, version information, and limitations so future agents can make
better technical decisions.

This is an evidence-gathering and documentation session. Do not change active
HAL, INI, firmware, tuning, wiring, or machine behavior as part of this task.
If an important change is discovered, document and propose it as a separate
workstream.

## Evidence to Gather

### LinuxCNC Runtime Identity

Capture exact output, using available equivalent commands when needed:

```bash
linuxcnc --version
dpkg-query -W linuxcnc-uspace linuxcnc-uspace-dev 2>/dev/null
uname -a
cat /etc/os-release
git -C /path/to/linuxcnc/source rev-parse HEAD 2>/dev/null
```

Determine whether the active runtime is stock LinuxCNC `2.9.6`, another package
version, or a locally patched build. Do not assume `CLAUDE.md` is current.

### Mesa Hardware and Firmware Identity

With LinuxCNC stopped if required for safe access, capture:

```bash
mesaflash --device 7i96s --addr 192.168.1.121 --readhmid
mesaflash --device 7i96s --addr 192.168.1.121 --read
```

Use the supported mesaflash syntax on the installed version. Save the exact
HostMot2 pin/module report, board identity, firmware/bitfile identity, and any
read-back checksum available. Do not flash or modify firmware.

### Physical Hardware Identity

With the machine safely powered down where appropriate, work with Jacob to
record clear label photographs and exact model/revision markings for:

- Both UIRobot UIM8696PM integrated closed-loop steppers
- Both SINO linear scales and readheads
- Spindle encoder
- Mesa 7i96S and 7i85S revisions
- Installed insert holders and inserts that will inform CAM defaults

Do not infer a model from appearance. Mark unreadable or inaccessible labels as
unknown.

### Vendor Documentation

Using exact observed model/revision identities, gather official manufacturer
manuals, configuration documentation, and datasheets where available:

- UIRobot UIM8696PM configuration, timing, limits, alarms, and software
- Exact SINO scale variants
- Exact spindle encoder
- Installed tooling/insert manufacturer data

Prefer official manufacturer sources. Record source URL, version/revision,
retrieval date, intended use, limitations, and SHA-256 for downloaded binaries.
Do not use an unattributed reseller document as authority.

## Reconciliation Work

Compare gathered evidence against:

- `industry-cam.ini`
- `industry-cam.hal`
- `CLAUDE.md`
- `docs/CURRENT_STATE.md`
- `reference/Hardware Integration Resources/`
- `reference/SINO WIRING MAP.csv`
- Newest commissioning notes

Explicitly list conflicts. Do not silently rewrite a current mapping based only
on an older reference or hardware manual. Current physical behavior and active
configuration still require verification.

## Required Deliverables

1. Add attributable reference files under an appropriate `reference/` folder.
2. Update `reference/INDEX.md`:
   - Close resolved acquisition gaps.
   - Record versions, authority, scope, and limitations.
   - Preserve unresolved gaps.
3. Update `docs/CURRENT_STATE.md` only for newly established durable facts.
4. Update `docs/RISK_REGISTER.md` if a risk materially changes.
5. Create a dated handoff using `docs/handoffs/TEMPLATE.md`.
6. Preserve raw command output and observations in a dated `session-notes/`
   file when useful.
7. Commit and push the focused branch, then report the branch, commit, evidence
   gathered, unresolved gaps, conflicts, and exact next step.

## Verification and Safety

- Label every conclusion as **Observed**, **Verified**, **Inferred**, or
  **Assumed**.
- Do not claim a manual applies until the exact installed model/revision is
  established.
- Do not energize motion merely to collect reference information.
- Do not modify or flash Mesa firmware.
- Do not overwrite active machine-state files.
- Stop if evidence gathering would require unsafe access or ambiguous machine
  changes.

## Acceptance Criteria

- Exact LinuxCNC runtime/package identity is recorded, or the reason it remains
  unknown is documented.
- Mesa identity and HostMot2/firmware evidence are captured without modification.
- Available physical hardware labels are recorded with Jacob.
- Official vendor documents are gathered where exact identity permits.
- `reference/INDEX.md` accurately distinguishes resolved and unresolved gaps.
- Conflicts with existing documentation are explicit.
- A structured handoff and focused commit are pushed.

---
