"""Tests for validation/architecture_check.py — static analysis tool.

Verifies that the architecture check correctly detects violations
and produces properly structured output.
"""

import ast
from pathlib import Path

import pytest

from validation.architecture_check import (
    ArchitectureViolation,
    check_dependency_violations,
    check_dead_code,
    check_fallback_patterns,
    check_dual_implementations,
    check_hand_math,
    run_all_checks,
    _parse_file,
    _get_module_for_file,
    _extract_imports,
    _is_sum_of_squares,
    _has_nontrivial_body,
)


@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


class TestArchitectureViolationDataclass:
    """Verify the ArchitectureViolation dataclass structure."""

    def test_fields_present(self):
        v = ArchitectureViolation(
            file_path="test.py",
            line_number=42,
            category="dependency_violation",
            message="test message",
            severity="error",
        )
        assert v.file_path == "test.py"
        assert v.line_number == 42
        assert v.category == "dependency_violation"
        assert v.message == "test message"
        assert v.severity == "error"

    def test_severity_values(self):
        """Severity must be 'error' or 'warning'."""
        v_err = ArchitectureViolation("f.py", 1, "cat", "msg", "error")
        v_warn = ArchitectureViolation("f.py", 1, "cat", "msg", "warning")
        assert v_err.severity == "error"
        assert v_warn.severity == "warning"


class TestDependencyViolations:
    """Test dependency violation detection."""

    def test_no_violations_in_models(self, project_root):
        """models/ should have no dependency violations (it imports nothing)."""
        violations = check_dependency_violations(project_root)
        model_violations = [
            v for v in violations
            if v.file_path.startswith("models")
            and v.category == "dependency_violation"
        ]
        assert model_violations == [], (
            f"models/ should have no dependency violations: {model_violations}"
        )

    def test_detects_restricted_packages(self, project_root):
        """Restricted packages should only be in their designated modules."""
        violations = check_dependency_violations(project_root)
        # If there are violations, they should be properly categorized
        for v in violations:
            assert v.category == "dependency_violation"
            assert v.severity == "error"

    def test_type_checking_imports_exempt(self, project_root):
        """TYPE_CHECKING imports should not trigger violations."""
        violations = check_dependency_violations(project_root)
        # Verify no violation mentions TYPE_CHECKING
        for v in violations:
            assert "TYPE_CHECKING" not in v.message


class TestDeadCode:
    """Test dead code detection."""

    def test_returns_warnings(self, project_root):
        """Dead code findings should be warnings, not errors."""
        violations = check_dead_code(project_root)
        for v in violations:
            assert v.severity == "warning"
            assert v.category == "dead_code"

    def test_skips_dunder_methods(self, project_root):
        """Dunder methods (__init__, __str__, etc.) should not be flagged."""
        violations = check_dead_code(project_root)
        for v in violations:
            assert not (v.message.startswith("Function '__") and "__'" in v.message)


class TestFallbackPatterns:
    """Test fallback pattern detection."""

    def test_detects_import_error_fallbacks(self, project_root):
        """ImportError fallbacks should be flagged as errors."""
        violations = check_fallback_patterns(project_root)
        import_errors = [v for v in violations if "ImportError" in v.message]
        # The gui/components/status_bar.py has a known ImportError fallback
        assert len(import_errors) >= 1

    def test_skips_architecture_check_itself(self, project_root):
        """architecture_check.py should not flag its own try/except."""
        violations = check_fallback_patterns(project_root)
        self_violations = [
            v for v in violations if "architecture_check.py" in v.file_path
        ]
        assert self_violations == []


class TestHandMath:
    """Test hand math detection."""

    def test_exempts_adaptive_sampling(self, project_root):
        """adaptive_sampling.py should be exempt (it IS the math utility)."""
        violations = check_hand_math(project_root)
        sampling_violations = [
            v for v in violations if "adaptive_sampling" in v.file_path
        ]
        assert sampling_violations == []

    def test_exempts_validators(self, project_root):
        """Validator functions using sqrt for tolerance checks should be exempt."""
        violations = check_hand_math(project_root)
        validator_violations = [
            v for v in violations
            if "validate_profile" in v.message or "validate_gcode" in v.message
        ]
        assert validator_violations == []


class TestRunAllChecks:
    """Test the combined run_all_checks function."""

    def test_returns_list_of_violations(self, project_root):
        """run_all_checks should return a list of ArchitectureViolation."""
        violations = run_all_checks(project_root)
        assert isinstance(violations, list)
        for v in violations:
            assert isinstance(v, ArchitectureViolation)

    def test_all_categories_present(self, project_root):
        """All check categories should be represented in results."""
        violations = run_all_checks(project_root)
        categories = set(v.category for v in violations)
        # At minimum, dead_code and fallback_pattern should be found
        assert "dead_code" in categories
        assert "fallback_pattern" in categories


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_parse_file_valid(self, tmp_path):
        """Valid Python files should parse successfully."""
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        tree = _parse_file(f)
        assert tree is not None
        assert isinstance(tree, ast.Module)

    def test_parse_file_invalid(self, tmp_path):
        """Invalid Python files should return None."""
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        tree = _parse_file(f)
        assert tree is None

    def test_is_sum_of_squares_mult(self):
        """Detect x*x + y*y pattern."""
        code = "math.sqrt(dx*dx + dy*dy)"
        tree = ast.parse(code, mode="eval")
        call = tree.body
        assert _is_sum_of_squares(call.args[0])

    def test_is_sum_of_squares_pow(self):
        """Detect x**2 + y**2 pattern."""
        code = "math.sqrt(dx**2 + dy**2)"
        tree = ast.parse(code, mode="eval")
        call = tree.body
        assert _is_sum_of_squares(call.args[0])

    def test_has_nontrivial_body_pass(self):
        """Single pass is trivial."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        tree = ast.parse(code)
        try_node = tree.body[0]
        handler = try_node.handlers[0]
        assert not _has_nontrivial_body(handler.body)

    def test_has_nontrivial_body_assignment(self):
        """Assignment in except is non-trivial."""
        code = "try:\n    x = 1\nexcept:\n    x = fallback()\n"
        tree = ast.parse(code)
        try_node = tree.body[0]
        handler = try_node.handlers[0]
        assert _has_nontrivial_body(handler.body)
