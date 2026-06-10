# Lathe Deployment and Rollback

This document defines the intended deployment discipline. It does not replace a
careful review of the exact change being deployed.

## Current Warning

Do not run `package_for_linux.py` from the current flattened repository layout.
The script still assumes it lives inside a dedicated output directory and may
attempt to clean the repository root. Repairing and testing the packager is a
separate work item.

Until deployment tooling is repaired, use a reviewed Git-based deployment or a
manually prepared package with an explicit file manifest.

## Pre-Deployment Requirements

- The deployment commit is identified.
- The source worktree is clean.
- Relevant automated and offline checks are recorded.
- Motion-affecting changes have a commissioning plan.
- A rollback commit or previous known-good copy is available.
- LinuxCNC is stopped before files are replaced.

## Files That Hold Machine State

Preserve these before deployment:

| File | Why |
|---|---|
| `industry-cam.var` | Work offsets and persistent LinuxCNC parameters |
| `tool.tbl` | Tool geometry and offsets |
| `industry-cam.ini` | Machine tuning and limits; reconcile rather than blindly overwrite |
| Commissioning JSON/state files | Setup progress and machine observations, if present |

HAL and GUI files are code/configuration, but still require review because they
can directly alter machine behavior.

## Deployment Record

Record the following in the session note:

```text
Source commit:
Previous machine commit/version:
Files changed:
Preserved machine-state files:
INI differences reviewed:
Expected behavior:
Commissioning limits:
Rollback location:
```

## Recommended Git-Based Procedure

The Linux machine should use a dedicated clone or checkout whose active commit
can be identified. Before updating:

```bash
git status --short --branch
git rev-parse HEAD
```

Preserve machine state outside the checkout:

```bash
mkdir -p ~/industry-cam-machine-backup
cp industry-cam.var ~/industry-cam-machine-backup/
cp tool.tbl ~/industry-cam-machine-backup/
cp industry-cam.ini ~/industry-cam-machine-backup/
```

Then update only to the reviewed commit. After update, compare the preserved INI
and tool table before restoring or merging values. Do not blindly restore an old
INI over a change that intentionally modifies machine control.

## Post-Deployment Checks

Before enabling motion:

1. Confirm the running checkout commit.
2. Review INI and HAL differences.
3. Confirm executable permissions on launcher scripts.
4. Start LinuxCNC with stepper power disabled when practical.
5. Confirm GUI and HAL load without errors.
6. Verify physical E-stop response.
7. Enable motion and perform the written commissioning plan at conservative limits.

## Rollback

Rollback means restoring both:

- A known-good code/configuration commit
- The matching preserved machine-state files

After rollback, repeat the same post-deployment checks. A rollback is not
considered complete merely because the GUI launches.

## Future Deployment Tool Requirements

The repaired deployment tool should:

- Never clean or overwrite the source repository.
- Build into a dedicated output directory.
- Produce a manifest containing source commit and file hashes.
- Exclude tests, references, caches, and local backups.
- Preserve or explicitly reconcile machine-state files.
- Support a dry run.
- Create a timestamped rollback package.
- Fail closed when the source worktree is dirty or ambiguous.
