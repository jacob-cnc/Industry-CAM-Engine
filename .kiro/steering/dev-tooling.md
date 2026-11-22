# Developer Tooling — Local Commands

This project uses a dedicated virtual environment at `.venv/`. Use it; do not rely
on a global `python`. This Windows authoring box has no system Python on PATH (a
bare `python` resolves to the Microsoft Store stub and there is no `py` launcher),
so always invoke tools through `.venv\Scripts\...`.

## The project venv

- **`.venv/`** — **Python 3.11** (3.11.9), chosen to match the lathe runtime. The
  lathe GUI runs Debian's Python 3.11.2 with LinuxCNC 2.9.6's `linuxcnc`/`hal`
  bindings built for it; `requirements-lathe.txt` is its exact dependency set and
  the suite is meant to run on those versions (`tests/test_runtime_env.py` pins
  them on Linux). Do NOT use Python 3.12/3.13 here — it would diverge from the
  lathe, which is the whole point of matching.
- Recreate it from the repo root (PowerShell) if the venv is missing:

```powershell
winget install --id Python.Python.3.11 -e
$py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $py -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements-lathe.txt
.venv\Scripts\python.exe -m pip install "PyQt5==5.15.9"   # Debian apt on the lathe; pip here
.venv\Scripts\python.exe -m pip install ruff mypy          # dev tools (advisory; not runtime, not on the lathe)
```

`requirements-lathe.txt` installs the full runtime set at the lathe's exact pins
(build123d, cadquery-ocp, vtk, shapely, ezdxf, numpy, scipy, matplotlib,
pyqtgraph, pytest, hypothesis, …). PyQt5 is not in that file because the lathe
gets it from Debian apt; install `PyQt5==5.15.9` here to match the binding
version.

## Running on Windows vs the lathe

- **No machine bindings.** `linuxcnc` and `hal` do not exist off the lathe; the
  suite's `conftest.py` makes them unimportable and runs against the mock backend.
  The GUI cannot fully launch here, but the test suite can.
- **Headless Qt.** There is no X display, so select the offscreen platform (and
  pin the lathe's DPI so pixel-budget layout tests measure the same thing):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"; $env:QT_FONT_DPI = "96"
.venv\Scripts\python.exe -m pytest -q
```

- **Qt runtime gap (known).** pip's `PyQt5-Qt5` wheel caps at Qt 5.15.2; the lathe
  runs Debian's Qt 5.15.9. The PyQt5 *binding* matches (5.15.9) but the C++ Qt
  runtime cannot on native Windows, so a few render/pixel-dependent GUI tests can
  differ here. The lathe (`scripts/run_tests.sh`, LinuxCNC down) is the authority.

## Standard commands

Run from the repo root (prefix the Qt env above for anything that builds widgets).

```powershell
# Tests (authoritative). scripts/run_tests.sh is the lathe equivalent (bash).
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

- **After any Python edit:** focused `pytest` for the changed module, then
  `ruff check` on the changed files. Fix what you touched; do not expand scope.
- **Before claiming a change is done:** full `pytest -q` and
  `validation.architecture_check`, per the Definition of Done in AGENTS.md. On
  Windows, mind the Qt-runtime caveat above and confirm on the lathe when it
  matters (motion, layout).
- **Architecture-sensitive changes:** `validation.architecture_check` is the
  authority on import direction, NOT Ruff. Ruff's import rules are cosmetic here.

## Discipline

- **Ruff and mypy are advisory.** The authoritative gates are the project's own
  `pytest` suite and `validation/architecture_check.py`. If a Ruff/mypy opinion
  conflicts with a project rule or steering file, the project wins.
- **Never bulk-apply `ruff --fix` across the repo.** `ruff check` reports a large
  pre-existing advisory backlog (import sorting, py311 modernization, unused
  imports). It is deliberate, not a batch edit — fixing it wholesale is an
  unreviewed, motion-adjacent change to a machine-control codebase, exactly what
  AGENTS.md warns against. Fix findings only in files you are already changing.
- **Config lives in `pyproject.toml`** (`[tool.ruff]`, `[tool.mypy]`). `backups/`,
  `.venv/`, `reference/`, and `point_charts/` are excluded as non-first-party.

## Baseline findings

These are pre-existing and drift with tool/code versions; run the tools for
current numbers rather than trusting a figure here.

- `validation.architecture_check`: FAILs on a baseline of pre-existing import
  findings (~15 errors as of 2026-11), unchanged by routine work.
- `ruff check`: thousands of advisory findings (mostly import sorting and py311
  modernization) — a deliberate backlog, not a to-do list.
- `mypy models`: a few pre-existing errors, e.g. `models/results.py` references an
  undefined `ValidationResult`. Flagged, not yet fixed.
