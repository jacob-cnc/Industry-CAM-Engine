"""Package Industry CAM Engine for deployment to Linux machine.

Run from the project root:
    python "Ship to LinuxPC/package_for_linux.py"

Produces a complete deployment package in 'Ship to LinuxPC/' containing:
  - All CAM engine modules (models → pipeline)
  - GUI with all tabs (including commissioning/tuning)
  - HAL abstraction layer
  - LinuxCNC config files (INI, HAL, var, launch script)
  - Tool table and requirements

The output folder can be copied directly to the LinuxCNC machine.
Target: /home/linuxcnc/linuxcnc/industry-cam/
"""

import os
import shutil
from pathlib import Path

# Project root is parent of this script's directory
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
OUTPUT_DIR = SCRIPT_DIR

# Directories to copy (source modules + HAL layer)
SOURCE_DIRS = [
    "models",
    "tools",
    "geometry",
    "intervals",
    "planners",
    "transitions",
    "validation",
    "outputs",
    "pipeline",
    "gui",
    "hal",
]

# LinuxCNC config files (deployed alongside the application)
LINUXCNC_DIR = "linuxcnc"

# Individual files to copy to the root of the package
ROOT_FILES = [
    "requirements.txt",
    "pyproject.toml",
    "tool.tbl",
]

# Files to preserve in the output directory (never delete these)
PRESERVE_FILES = {"README.md", "package_for_linux.py"}


def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from packaging."""
    for part in path.parts:
        if part == "__pycache__":
            return True
        if part == ".pytest_cache":
            return True
        if part == ".git":
            return True
    if path.suffix in (".pyc", ".pyo"):
        return True
    return False


def copy_directory(src_dir: Path, dst_dir: Path) -> int:
    """Copy a directory, excluding __pycache__ and .pyc files.

    Returns the number of files copied.
    """
    count = 0
    for item in src_dir.rglob("*"):
        if should_exclude(item):
            continue
        if item.is_file():
            rel = item.relative_to(src_dir)
            dest = dst_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            count += 1
    return count


def main():
    print("=" * 60)
    print("  Industry CAM Engine — Linux Deployment Packager")
    print("=" * 60)
    print(f"  Source: {PROJECT_ROOT}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # --- Clean previous package (preserve README and this script) ---
    print("Cleaning previous package...")
    for item in OUTPUT_DIR.iterdir():
        if item.name in PRESERVE_FILES:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        elif item.is_file():
            item.unlink()
    print()

    # --- Copy source directories ---
    print("Copying source modules:")
    total_files = 0
    for dir_name in SOURCE_DIRS:
        src = PROJECT_ROOT / dir_name
        dst = OUTPUT_DIR / dir_name
        if src.is_dir():
            count = copy_directory(src, dst)
            total_files += count
            print(f"  ✓ {dir_name}/ ({count} files)")
        else:
            print(f"  ✗ {dir_name}/ NOT FOUND — skipping")
    print()

    # --- Copy LinuxCNC config files ---
    print("Copying LinuxCNC configuration:")
    linuxcnc_src = PROJECT_ROOT / LINUXCNC_DIR
    if linuxcnc_src.is_dir():
        # Copy linuxcnc/ contents to the OUTPUT root (they sit alongside gui/)
        for item in linuxcnc_src.iterdir():
            if item.is_file():
                dest = OUTPUT_DIR / item.name
                shutil.copy2(item, dest)
                total_files += 1
                print(f"  ✓ {item.name}")
    else:
        print(f"  ✗ {LINUXCNC_DIR}/ NOT FOUND — skipping")
    print()

    # --- Copy root files ---
    print("Copying support files:")
    for file_name in ROOT_FILES:
        src = PROJECT_ROOT / file_name
        dst = OUTPUT_DIR / file_name
        if src.is_file():
            shutil.copy2(src, dst)
            total_files += 1
            print(f"  ✓ {file_name}")
        else:
            print(f"  ✗ {file_name} NOT FOUND — skipping")
    print()

    # --- Create runtime requirements (exclude test deps) ---
    runtime_req = OUTPUT_DIR / "requirements.txt"
    if runtime_req.exists():
        lines = runtime_req.read_text().splitlines()
        filtered = [l for l in lines if not l.strip().startswith("hypothesis")]
        runtime_req.write_text("\n".join(filtered) + "\n")
        print("  ✓ Removed hypothesis from requirements.txt (test-only dep)")
    print()

    # --- Summary ---
    total_size = sum(
        f.stat().st_size for f in OUTPUT_DIR.rglob("*") if f.is_file()
    )
    py_count = sum(1 for _ in OUTPUT_DIR.rglob("*.py"))
    print("=" * 60)
    print(f"  Package complete!")
    print(f"  Python files: {py_count}")
    print(f"  Total files:  {total_files}")
    print(f"  Total size:   {total_size / 1024:.0f} KB ({total_size / 1048576:.1f} MB)")
    print()
    print("  Deploy to LinuxCNC machine:")
    print(f'    scp -r "{OUTPUT_DIR}" linuxcnc@<machine-ip>:~/linuxcnc/industry-cam')
    print()
    print("  Or copy via USB drive to:")
    print("    /home/linuxcnc/linuxcnc/industry-cam/")
    print()
    print("  Then launch:")
    print("    linuxcnc ~/linuxcnc/industry-cam/industry-cam.ini")
    print("=" * 60)


if __name__ == "__main__":
    main()
