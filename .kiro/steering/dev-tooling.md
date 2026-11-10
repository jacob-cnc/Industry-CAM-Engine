# Developer Tooling — Local Commands

This project has a dedicated virtual environment and a small set of trusted CLI
tools installed locally. Use them; do not assume global installs exist. The
system `python` on this machine is 3.15 (too new for build123d/OCP wheels) — the
`.venv` is Python 3.12 and is the correct interpreter for this project.

> **Do not use system Python / the `py` launcher for this project.** The machine's
> system Python is 3.15 to satisfy a corporate compliance policy (ACME requires a
> minimum version). build123d/OCP have no 3.15 wheels, so running `python` or `py`
> directly in this repo will fail on import. The project depends ONLY on uv's
> managed CPython 3.12 — the `.venv`'s `base_prefix` points at
> `AppData\Roaming\uv\python\cpython-3.12-...`, NOT at the system install. As a
> result the environment is unaffected if the system `py` launcher is updated or
> uninstalled for compliance. Always invoke tools via `.venv\Scripts\...`.

## Where the tools live

- **Project venv:** `.venv/` (Python 3.12). Dev tools are installed here.
  - `ruff`   -> `.venv\Scripts\ruff.exe`
  - `mypy`   -> `.venv\Scripts\mypy.exe`
  - `pytest` -> `.venv\Scripts\python.exe -m pytest`
- **User-level binaries (on PATH after shell restart):**
  - `uv`  — Python package/venv manager (`~/.local/bin`)
  - `rg`  — ripgrep, fast search (winget, BurntSushi.ripgrep.MSVC)
  - `fd`  — fast file find (winget, sharkdp.fd)

The `.venv` holds dev tools only. Runtime deps (build123d, PyQt5, pyqtgraph,
shapely, ezdxf, numpy, matplotlib, hypothesis) are NOT installed there yet; add
them with `uv pip install --python .venv -r requirements.txt` when runtime
execution or GUI work is needed.

## Standard commands (match AGENTS.md "Verification Expectations")

Run from the repo root.

```powershell
# Tests (authoritative)
.venv\Scripts\python.exe -m pytest -q

# Architecture gate (authoritative — the real import-direction enforcement)
.venv\Scripts\python.exe -m validation.architecture_check

# Lint (advisory): report only, never bulk-fix a safety-critical tree unasked
.venv\Scripts\ruff.exe check .

# Format check (advisory)
.venv\Scripts\ruff.exe format --check .

# Type check (advisory)
.venv\Scripts\mypy.exe <module>
```

## When to run what

- **After any Python edit:** run focused `pytest` for the changed module, then
  `ruff check` on the changed files. Fix what you touched; do not expand scope.
- **Before claiming a change is done:** run the full `pytest -q` and
  `validation.architecture_check`, per the Definition of Done in AGENTS.md.
- **Architecture-sensitive changes:** `validation.architecture_check` is the
  authority on import direction, NOT Ruff. Ruff's import rules are cosmetic here.

## Discipline

- **Ruff and mypy are advisory.** The authoritative gates remain the project's
  own `pytest` suite and `validation/architecture_check.py`. If a Ruff/mypy
  opinion conflicts with a project rule or steering file, the project wins.
- **Never bulk-apply `ruff --fix` across the repo.** The first baseline run
  reported ~1400 findings (mostly import sorting and py311 modernization). These
  are a deliberate backlog, not a batch edit. Fixing them wholesale is an
  unreviewed, motion-adjacent change to a machine-control codebase — exactly what
  AGENTS.md warns against. Fix findings in the files you are already changing.
- **Config lives in `pyproject.toml`** (`[tool.ruff]`, `[tool.mypy]`). `backups/`,
  `.venv/`, `reference/`, and `point_charts/` are excluded as non-first-party.

## Known baseline findings (as of install)

- `ruff check`: ~1422 findings — 235 unused imports (F401) and 23 unused vars
  (F841) map to the "no dead code" hard rule and are real cleanup candidates;
  `import *` usage (F403/F405) is worth a human look.
- `mypy models`: `models/results.py:85` references an undefined `ValidationResult`
  — possible missing import or forward-ref. Flagged, not yet fixed.
