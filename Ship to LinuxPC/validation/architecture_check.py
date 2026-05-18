"""Static architecture analysis for Industry CAM Engine.

Detects dependency violations, dead code, fallback patterns, dual implementations,
and hand math violations using AST-based source analysis.

This is a STATIC analysis tool — it reads source files, it doesn't execute them.
Uses ast module for parsing, pathlib for file discovery.

Runnable standalone: python -m validation.architecture_check

Imports from: nothing (stdlib only — ast, pathlib, dataclasses)
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional


@dataclass
class ArchitectureViolation:
    """A single architecture check finding."""
    file_path: str
    line_number: int
    category: str
    message: str
    severity: str  # "error" | "warning"


# Module dependency chain (strict left-to-right)
# Each module may only import from modules to its LEFT in this list.
MODULE_ORDER = [
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
]

# Allowed imports for each module (derived from the dependency chain + spec rules)
ALLOWED_IMPORTS: Dict[str, Set[str]] = {
    "models": set(),  # imports NOTHING external
    "tools": {"models"},
    "geometry": {"models", "tools"},
    "intervals": {"models", "geometry"},
    "planners": {"models", "tools", "intervals"},
    "transitions": {"models", "intervals"},
    "validation": {"models", "geometry"},
    "outputs": {"models"},
    "pipeline": {"models", "tools", "geometry", "intervals", "planners",
                 "transitions", "validation", "outputs"},
    "gui": {"models", "tools", "geometry", "intervals", "planners",
            "transitions", "validation", "outputs", "pipeline"},
}

# Directories to skip during analysis
SKIP_DIRS = {"__pycache__", "reference", "tests", ".git", ".kiro", ".pytest_cache"}

# Restricted external packages per module
RESTRICTED_PACKAGES: Dict[str, Set[str]] = {
    "build123d": {"geometry"},  # Only geometry/ may import build123d
    "OCP": {"geometry"},        # Only geometry/ may import OCP
    "shapely": {"validation"},  # Only validation/ may import shapely
    "pyqtgraph": {"gui"},       # Only gui/ may import pyqtgraph
    "PyQt5": {"gui"},           # Only gui/ may import PyQt5
}


# Hand math patterns to detect
HAND_MATH_MODULES = {"geometry", "planners", "validation"}

# Files exempt from hand math checks (they ARE the math utilities or validators)
HAND_MATH_EXEMPT_FILES = {
    "adaptive_sampling.py",      # Intentionally uses trig for polygon densification
    "architecture_check.py",     # This file — static analysis tool
}

# Functions exempt from hand math sqrt checks (tolerance validation is allowed)
HAND_MATH_EXEMPT_FUNCTIONS = {
    "validate_profile",          # Uses sqrt for arc radius validation (tolerance check)
    "validate_gcode_geometry",   # Uses sqrt for arc endpoint validation (tolerance check)
    "flatness_predicate",        # Densification utility — intentional math
    "arc_midpoint",              # Densification utility — intentional math
    "adaptive_densify_arc",      # Densification utility — intentional math
}

# Modules where fallback patterns are flagged
FALLBACK_MODULES = {"geometry", "planners", "validation"}


def _get_project_modules(project_root: Path) -> List[str]:
    """Get list of project module directories that exist."""
    return [m for m in MODULE_ORDER if (project_root / m).is_dir()]


def _get_python_files(project_root: Path) -> List[Path]:
    """Discover all .py files in project modules, skipping excluded dirs."""
    files = []
    for module_name in _get_project_modules(project_root):
        module_dir = project_root / module_name
        for py_file in module_dir.rglob("*.py"):
            # Skip excluded directories
            if any(part in SKIP_DIRS for part in py_file.parts):
                continue
            files.append(py_file)
    return files


def _get_module_for_file(file_path: Path, project_root: Path) -> Optional[str]:
    """Determine which module a file belongs to based on its directory."""
    try:
        rel = file_path.relative_to(project_root)
        parts = rel.parts
        if parts and parts[0] in MODULE_ORDER:
            return parts[0]
    except ValueError:
        pass
    return None


def _parse_file(file_path: Path) -> Optional[ast.Module]:
    """Parse a Python file into an AST. Returns None on parse failure."""
    try:
        source = file_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return None  # Unparseable files are silently skipped


def _extract_imports(tree: ast.Module) -> List[Tuple[int, str, bool]]:
    """Extract all imports from an AST.

    Returns list of (line_number, module_name, is_type_checking).
    """
    imports = []
    type_checking_ranges = _get_type_checking_ranges(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                in_tc = _in_type_checking(node.lineno, type_checking_ranges)
                imports.append((node.lineno, alias.name, in_tc))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                in_tc = _in_type_checking(node.lineno, type_checking_ranges)
                imports.append((node.lineno, node.module, in_tc))

    return imports


def _get_type_checking_ranges(tree: ast.Module) -> List[Tuple[int, int]]:
    """Find line ranges inside `if TYPE_CHECKING:` blocks."""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # Check if the test is TYPE_CHECKING
            if _is_type_checking_test(node.test):
                start = node.lineno
                end = node.end_lineno or start
                ranges.append((start, end))
    return ranges


def _is_type_checking_test(node: ast.expr) -> bool:
    """Check if an expression is TYPE_CHECKING."""
    if isinstance(node, ast.Name) and node.id == "TYPE_CHECKING":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING":
        return True
    return False


def _in_type_checking(lineno: int, ranges: List[Tuple[int, int]]) -> bool:
    """Check if a line number falls within a TYPE_CHECKING block."""
    for start, end in ranges:
        if start <= lineno <= end:
            return True
    return False


def _get_top_level_module(import_name: str) -> str:
    """Extract the top-level module from a dotted import path."""
    return import_name.split(".")[0]


# ---------------------------------------------------------------------------
# Check 1: Dependency Violation Detection
# ---------------------------------------------------------------------------

def check_dependency_violations(project_root: Path) -> List[ArchitectureViolation]:
    """Detect imports that violate the module dependency chain.

    Rules:
    - Each module may only import from modules LEFT of it in MODULE_ORDER
    - TYPE_CHECKING imports are exempt (they don't create runtime dependencies)
    - Restricted packages (build123d, shapely, etc.) may only be imported
      by their designated modules
    """
    violations = []
    project_modules = set(_get_project_modules(project_root))

    for py_file in _get_python_files(project_root):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        source_module = _get_module_for_file(py_file, project_root)
        if source_module is None:
            continue

        imports = _extract_imports(tree)
        allowed = ALLOWED_IMPORTS.get(source_module, set())

        for lineno, import_name, is_type_checking in imports:
            top_module = _get_top_level_module(import_name)

            # Skip TYPE_CHECKING imports — they don't create runtime deps
            if is_type_checking:
                continue

            # Check internal module dependency violations
            if top_module in project_modules and top_module != source_module:
                if top_module not in allowed:
                    violations.append(ArchitectureViolation(
                        file_path=str(py_file.relative_to(project_root)),
                        line_number=lineno,
                        category="dependency_violation",
                        message=(
                            f"Module '{source_module}' imports '{import_name}' "
                            f"but is only allowed to import from: "
                            f"{sorted(allowed) if allowed else '(nothing)'}"
                        ),
                        severity="error",
                    ))

            # Check restricted external package violations
            for pkg, allowed_modules in RESTRICTED_PACKAGES.items():
                if top_module == pkg and source_module not in allowed_modules:
                    violations.append(ArchitectureViolation(
                        file_path=str(py_file.relative_to(project_root)),
                        line_number=lineno,
                        category="dependency_violation",
                        message=(
                            f"Package '{pkg}' may only be imported by "
                            f"{sorted(allowed_modules)}, but found in '{source_module}'"
                        ),
                        severity="error",
                    ))

    return violations


# ---------------------------------------------------------------------------
# Check 2: Dead Code Detection
# ---------------------------------------------------------------------------

def check_dead_code(project_root: Path) -> List[ArchitectureViolation]:
    """Detect functions/classes with zero callers and unused imports.

    Exclusions:
    - __init__, __main__, __str__, __repr__ and other dunder methods
    - Test files (tests/ directory)
    - Functions/classes in __init__.py (public API exports)
    - Decorated functions (may be registered via framework)
    """
    violations = []

    # Phase 1: Collect all defined names and all referenced names
    definitions: List[Tuple[str, str, int, str]] = []  # (name, file, line, kind)
    references: Set[str] = set()

    py_files = _get_python_files(project_root)

    for py_file in py_files:
        tree = _parse_file(py_file)
        if tree is None:
            continue

        rel_path = str(py_file.relative_to(project_root))
        is_init = py_file.name == "__init__.py"

        # Collect definitions (top-level functions and classes only)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                name = node.name
                # Skip dunder methods and private helpers starting with _
                if name.startswith("__") and name.endswith("__"):
                    continue
                # Skip __init__.py definitions (public API)
                if is_init:
                    continue
                # Skip decorated functions (may be registered externally)
                if node.decorator_list:
                    continue
                definitions.append((name, rel_path, node.lineno, "function"))

            elif isinstance(node, ast.ClassDef):
                name = node.name
                if is_init:
                    continue
                if node.decorator_list:
                    continue
                definitions.append((name, rel_path, node.lineno, "class"))

        # Collect all name references in the file
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                references.add(node.id)
            elif isinstance(node, ast.Attribute):
                references.add(node.attr)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    references.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    references.add(node.func.attr)

    # Also scan test files for references (tests call production code)
    test_dir = project_root / "tests"
    if test_dir.is_dir():
        for py_file in test_dir.rglob("*.py"):
            tree = _parse_file(py_file)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    references.add(node.id)
                elif isinstance(node, ast.Attribute):
                    references.add(node.attr)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        references.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        references.add(node.func.attr)

    # Phase 2: Report definitions with zero references
    for name, file_path, lineno, kind in definitions:
        if name not in references:
            violations.append(ArchitectureViolation(
                file_path=file_path,
                line_number=lineno,
                category="dead_code",
                message=f"{kind.capitalize()} '{name}' has zero callers/references",
                severity="warning",
            ))

    # Phase 3: Detect unused imports
    for py_file in py_files:
        tree = _parse_file(py_file)
        if tree is None:
            continue

        rel_path = str(py_file.relative_to(project_root))
        is_init = py_file.name == "__init__.py"

        # Skip __init__.py — re-exports are intentional
        if is_init:
            continue

        # Collect imported names in this file
        imported_names: List[Tuple[str, int]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname if alias.asname else alias.name.split(".")[-1]
                    imported_names.append((local_name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.names:
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        local_name = alias.asname if alias.asname else alias.name
                        imported_names.append((local_name, node.lineno))

        # Collect all names used in the file (excluding import statements)
        used_names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_names.add(node.attr)

        # Also check string annotations (TYPE_CHECKING forward refs)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Could be a string annotation like 'ZoneQueryAPI'
                used_names.add(node.value)

        for name, lineno in imported_names:
            if name not in used_names and name != "TYPE_CHECKING":
                violations.append(ArchitectureViolation(
                    file_path=rel_path,
                    line_number=lineno,
                    category="dead_code",
                    message=f"Unused import: '{name}'",
                    severity="warning",
                ))

    return violations


# ---------------------------------------------------------------------------
# Check 3: Fallback Pattern Detection
# ---------------------------------------------------------------------------

def check_fallback_patterns(project_root: Path) -> List[ArchitectureViolation]:
    """Detect try/except blocks that provide alternative implementations.

    Flags:
    - try/except ImportError with alternative code path
    - try/except with non-trivial except body in geometry/, planners/, validation/
    - if hasattr(...) patterns selecting between two code paths
    """
    violations = []

    for py_file in _get_python_files(project_root):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        rel_path = str(py_file.relative_to(project_root))
        source_module = _get_module_for_file(py_file, project_root)

        # Skip this file itself — it uses try/except for file parsing, not fallbacks
        if py_file.name == "architecture_check.py":
            continue

        for node in ast.walk(tree):
            # Detect try/except with alternative implementations
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    # Check for ImportError catches with fallback
                    is_import_error = False
                    if handler.type is not None:
                        if isinstance(handler.type, ast.Name):
                            is_import_error = handler.type.id == "ImportError"
                        elif isinstance(handler.type, ast.Tuple):
                            for elt in handler.type.elts:
                                if isinstance(elt, ast.Name) and elt.id == "ImportError":
                                    is_import_error = True

                    if is_import_error and _has_nontrivial_body(handler.body):
                        violations.append(ArchitectureViolation(
                            file_path=rel_path,
                            line_number=node.lineno,
                            category="fallback_pattern",
                            message=(
                                "try/except ImportError with alternative implementation — "
                                "violates 'no silent fallbacks' principle (P3)"
                            ),
                            severity="error",
                        ))

                    # In critical modules, flag any non-trivial except body
                    elif (source_module in FALLBACK_MODULES
                          and _has_nontrivial_body(handler.body)):
                        # Allow bare `raise` or logging-only handlers
                        if not _is_reraise_or_log_only(handler.body):
                            violations.append(ArchitectureViolation(
                                file_path=rel_path,
                                line_number=node.lineno,
                                category="fallback_pattern",
                                message=(
                                    f"try/except in '{source_module}/' with non-trivial "
                                    f"except body — potential fallback pattern"
                                ),
                                severity="warning",
                            ))

            # Detect if hasattr(...) patterns
            if isinstance(node, ast.If):
                if _is_hasattr_check(node.test):
                    violations.append(ArchitectureViolation(
                        file_path=rel_path,
                        line_number=node.lineno,
                        category="fallback_pattern",
                        message=(
                            "if hasattr(...) pattern — may indicate dual code path "
                            "selection for the same operation"
                        ),
                        severity="warning",
                    ))

    return violations


def _has_nontrivial_body(body: List[ast.stmt]) -> bool:
    """Check if a statement body is non-trivial (more than pass/raise/comment)."""
    if not body:
        return False
    # Single pass statement
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return False
    # Single raise statement (re-raise)
    if len(body) == 1 and isinstance(body[0], ast.Raise):
        return False
    # Single expression that's just a string (docstring/comment)
    if (len(body) == 1 and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return False
    return True


def _is_reraise_or_log_only(body: List[ast.stmt]) -> bool:
    """Check if except body only re-raises or logs."""
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            # Allow logging calls
            func = stmt.value.func
            if isinstance(func, ast.Attribute):
                if func.attr in ("debug", "info", "warning", "error", "critical",
                                 "exception", "log"):
                    continue
            if isinstance(func, ast.Name) and func.id == "print":
                continue
        return False
    return True


def _is_hasattr_check(node: ast.expr) -> bool:
    """Check if an expression is a hasattr() call."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "hasattr":
            return True
    return False


# ---------------------------------------------------------------------------
# Check 4: Dual Implementation Detection
# ---------------------------------------------------------------------------

def check_dual_implementations(project_root: Path) -> List[ArchitectureViolation]:
    """Detect two functions computing the same geometric quantity.

    Looks for:
    - Multiple functions with similar names suggesting same computation
      (e.g., two offset functions, two arc center functions)
    - Functions in different modules that implement the same geometric operation
    """
    violations = []

    # Collect all function definitions with their module
    func_defs: List[Tuple[str, str, int, str]] = []  # (name, file, line, module)

    for py_file in _get_python_files(project_root):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        rel_path = str(py_file.relative_to(project_root))
        source_module = _get_module_for_file(py_file, project_root)
        if source_module is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private/dunder methods
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                func_defs.append((node.name, rel_path, node.lineno, source_module))

    # Geometric operation keywords that suggest same computation
    geometric_keywords = [
        "offset", "arc_center", "boundary", "intersection", "distance",
        "crossing", "contour", "polygon", "densif",
    ]

    # Group functions by geometric keyword
    keyword_groups: Dict[str, List[Tuple[str, str, int, str]]] = {}
    for name, file_path, lineno, module in func_defs:
        name_lower = name.lower()
        for keyword in geometric_keywords:
            if keyword in name_lower:
                key = keyword
                if key not in keyword_groups:
                    keyword_groups[key] = []
                keyword_groups[key].append((name, file_path, lineno, module))

    # Flag groups where multiple functions exist in different modules
    # (same module is OK if they handle different cases, e.g. OD vs ID)
    for keyword, funcs in keyword_groups.items():
        if len(funcs) < 2:
            continue

        # Check for cross-module duplicates (excluding pipeline which orchestrates)
        modules_seen: Dict[str, List[Tuple[str, str, int]]] = {}
        for name, file_path, lineno, module in funcs:
            if module == "pipeline":
                continue
            if module not in modules_seen:
                modules_seen[module] = []
            modules_seen[module].append((name, file_path, lineno))

        # Flag if same geometric keyword appears in modules that shouldn't both
        # implement it (e.g., geometry/ and outputs/ both computing offsets)
        if len(modules_seen) > 1:
            # Only flag specific problematic combinations
            module_set = set(modules_seen.keys())
            problematic_pairs = [
                {"geometry", "outputs"},
                {"geometry", "planners"},
                {"planners", "outputs"},
            ]
            for pair in problematic_pairs:
                if pair.issubset(module_set):
                    all_funcs = []
                    for m in pair:
                        all_funcs.extend(modules_seen[m])
                    if len(all_funcs) >= 2:
                        first = all_funcs[0]
                        violations.append(ArchitectureViolation(
                            file_path=first[1],
                            line_number=first[2],
                            category="dual_implementation",
                            message=(
                                f"Potential dual implementation: '{keyword}' operations "
                                f"found in modules {sorted(pair)}. "
                                f"Functions: {[f[0] for f in all_funcs]}"
                            ),
                            severity="warning",
                        ))

    return violations


# ---------------------------------------------------------------------------
# Check 5: Hand Math Detection
# ---------------------------------------------------------------------------

def check_hand_math(project_root: Path) -> List[ArchitectureViolation]:
    """Detect manual geometric computations that should use Build123d.

    Patterns flagged:
    - math.atan2 + math.cos/math.sin in same function (arc center computation)
    - sqrt(dx*dx + dy*dy) patterns (distance computation)
    - Functions in geometry/ or planners/ computing offsets without Build123d calls
    - Coordinate arithmetic with fin_allowance, offset, doc, radius
    """
    violations = []

    for py_file in _get_python_files(project_root):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        rel_path = str(py_file.relative_to(project_root))
        source_module = _get_module_for_file(py_file, project_root)

        # Only check modules where hand math is problematic
        if source_module not in HAND_MATH_MODULES:
            continue

        # Skip exempt files (math utilities, validators that need sqrt)
        if py_file.name in HAND_MATH_EXEMPT_FILES:
            continue

        # Analyze each function for hand math patterns
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name

            # Skip exempt functions (tolerance validators, densification utils)
            if func_name in HAND_MATH_EXEMPT_FUNCTIONS:
                continue

            func_violations = _check_function_for_hand_math(
                node, func_name, rel_path, source_module
            )
            violations.extend(func_violations)

    return violations


def _check_function_for_hand_math(
    func_node: ast.FunctionDef,
    func_name: str,
    file_path: str,
    module: str,
) -> List[ArchitectureViolation]:
    """Check a single function for hand math patterns."""
    violations = []

    # Collect all math function calls in this function
    math_calls: Set[str] = set()
    has_sqrt = False
    has_atan2 = False
    has_trig = False  # cos or sin

    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name:
                math_calls.add(call_name)
                if "sqrt" in call_name:
                    has_sqrt = True
                if "atan2" in call_name:
                    has_atan2 = True
                if call_name in ("math.cos", "math.sin", "cos", "sin"):
                    has_trig = True

    # Pattern 1: atan2 + cos/sin in same function = manual arc center
    if has_atan2 and has_trig:
        violations.append(ArchitectureViolation(
            file_path=file_path,
            line_number=func_node.lineno,
            category="hand_math",
            message=(
                f"Function '{func_name}' uses atan2 + cos/sin — "
                f"likely manual arc center computation. "
                f"Use Build123d kernel operations instead."
            ),
            severity="error",
        ))

    # Pattern 2: sqrt with coordinate-like multiplication (distance formula)
    if has_sqrt:
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call) and _get_call_name(node) in ("math.sqrt", "sqrt"):
                if node.args and _is_sum_of_squares(node.args[0]):
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        line_number=node.lineno,
                        category="hand_math",
                        message=(
                            f"Function '{func_name}' computes sqrt(dx² + dy²) — "
                            f"manual distance formula. "
                            f"Use Build123d distance operations instead."
                        ),
                        severity="error",
                    ))
                    break  # One violation per function is enough

    # Pattern 3: Coordinate arithmetic with offset-related variables
    offset_vars = {"fin_allowance", "offset", "doc", "doc_dia"}
    for node in ast.walk(func_node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            # Check if one side is a coordinate-like name and other is offset-like
            left_names = _extract_names(node.left)
            right_names = _extract_names(node.right)
            all_names = left_names | right_names

            coord_names = {"x", "z", "center_x", "center_z", "start_x", "start_z",
                          "end_x", "end_z", "profile_x", "profile_z"}
            has_coord = bool(all_names & coord_names)
            has_offset = bool(all_names & offset_vars)

            if has_coord and has_offset:
                # Allow diameter/radius conversions and tolerance checks
                if not _is_allowed_arithmetic(node):
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        line_number=node.lineno,
                        category="hand_math",
                        message=(
                            f"Function '{func_name}' has coordinate arithmetic "
                            f"with offset variable — manual offset computation. "
                            f"Use geometry kernel offset() instead."
                        ),
                        severity="error",
                    ))
                    break  # One per function

    return violations


def _get_call_name(node: ast.Call) -> Optional[str]:
    """Get the full dotted name of a function call."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}"
        return node.func.attr
    return None


def _is_sum_of_squares(node: ast.expr) -> bool:
    """Check if an expression looks like dx*dx + dy*dy or dx**2 + dy**2."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_square_term(node.left) and _is_square_term(node.right)
    return False


def _is_square_term(node: ast.expr) -> bool:
    """Check if an expression is x*x or x**2."""
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mult):
            # x * x pattern
            if (isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name)
                    and node.left.id == node.right.id):
                return True
        elif isinstance(node.op, ast.Pow):
            # x ** 2 pattern
            if (isinstance(node.right, ast.Constant)
                    and node.right.value == 2):
                return True
    return False


def _extract_names(node: ast.expr) -> Set[str]:
    """Extract all Name identifiers from an expression."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


def _is_allowed_arithmetic(node: ast.BinOp) -> bool:
    """Check if arithmetic is one of the allowed patterns.

    Allowed:
    - Diameter/radius conversion: x / 2.0, x * 2.0
    - Tolerance comparison context (handled elsewhere)
    - Pass level computation: stock_dia - n * doc_dia
    """
    # Division or multiplication by 2 (diameter/radius conversion)
    if isinstance(node.op, (ast.Div, ast.Mult)):
        if isinstance(node.right, ast.Constant) and node.right.value in (2, 2.0):
            return True
        if isinstance(node.left, ast.Constant) and node.left.value in (2, 2.0):
            return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_all_checks(project_root: Path) -> List[ArchitectureViolation]:
    """Run all architecture checks and return combined violation list.

    Checks performed:
    1. Dependency violations (AST-based import analysis)
    2. Dead code (functions/classes with zero callers, unused imports)
    3. Fallback patterns (try/except with alternative implementations)
    4. Dual implementations (two functions computing same geometric quantity)
    5. Hand math (manual arc center, circle intersection, offset formulas)
    """
    project_root = Path(project_root).resolve()

    all_violations: List[ArchitectureViolation] = []
    all_violations.extend(check_dependency_violations(project_root))
    all_violations.extend(check_dead_code(project_root))
    all_violations.extend(check_fallback_patterns(project_root))
    all_violations.extend(check_dual_implementations(project_root))
    all_violations.extend(check_hand_math(project_root))

    return all_violations


def print_report(violations: List[ArchitectureViolation]) -> None:
    """Print a formatted report of all violations."""
    if not violations:
        print("✓ All architecture checks passed — no violations found.")
        return

    # Group by category
    by_category: Dict[str, List[ArchitectureViolation]] = {}
    for v in violations:
        if v.category not in by_category:
            by_category[v.category] = []
        by_category[v.category].append(v)

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    print("=" * 70)
    print("ARCHITECTURE CHECK REPORT")
    print("=" * 70)
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Total:    {len(violations)}")
    print()

    category_labels = {
        "dependency_violation": "Dependency Violations",
        "dead_code": "Dead Code",
        "fallback_pattern": "Fallback Patterns",
        "dual_implementation": "Dual Implementations",
        "hand_math": "Hand Math",
    }

    for category, category_violations in sorted(by_category.items()):
        label = category_labels.get(category, category)
        status = "FAIL" if any(v.severity == "error" for v in category_violations) else "WARN"
        print(f"[{status}] {label} ({len(category_violations)} issues)")
        print("-" * 50)
        for v in category_violations:
            severity_marker = "ERROR" if v.severity == "error" else "WARN "
            print(f"  [{severity_marker}] {v.file_path}:{v.line_number}")
            print(f"           {v.message}")
        print()

    print("=" * 70)
    if errors:
        print(f"RESULT: FAIL ({len(errors)} errors must be fixed)")
    else:
        print(f"RESULT: PASS ({len(warnings)} warnings — informational only)")
    print("=" * 70)


def main() -> int:
    """CLI entry point for standalone execution."""
    # Determine project root
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1])
    else:
        # Default: assume we're run from the project root or validation/ dir
        candidate = Path.cwd()
        if candidate.name == "validation":
            candidate = candidate.parent
        project_root = candidate

    if not project_root.is_dir():
        print(f"Error: Project root not found: {project_root}", file=sys.stderr)
        return 1

    # Verify it looks like the right project
    if not (project_root / "models").is_dir():
        print(f"Error: '{project_root}' doesn't look like Industry CAM Engine "
              f"(no models/ directory)", file=sys.stderr)
        return 1

    print(f"Analyzing: {project_root}")
    print()

    violations = run_all_checks(project_root)
    print_report(violations)

    # Exit code: 1 if any errors, 0 otherwise (warnings don't fail)
    errors = [v for v in violations if v.severity == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
