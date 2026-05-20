"""Unit tests for pipeline.tool_table_io — ToolTableSerializer module.

Tests serialization, deserialization, file I/O, and backup creation.
"""

import os
import tempfile

import pytest

from pipeline.tool_card_data import ToolCardData
from pipeline.tool_table_io import (
    serialize_tool,
    deserialize_tool,
    save_tool_table,
    load_tool_table,
    create_backup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_tool():
    """A typical turning tool."""
    return ToolCardData(
        tool_number=1,
        tool_type="Turning RH",
        insert_code="CNMG",
        orientation=1,
        description="CNMG 432 roughing",
        nose_radius=0.016,
        front_angle=95.0,
        back_angle=175.0,
        x_offset=0.0,
        z_offset=-1.234567,
        x_wear=0.001,
        z_wear=-0.002,
        blade_width=0.0,
    )


@pytest.fixture
def boring_tool():
    """A boring bar tool with non-zero X offset."""
    return ToolCardData(
        tool_number=2,
        tool_type="Boring Bar",
        insert_code="DCMT",
        orientation=5,
        description="DCMT boring",
        nose_radius=0.016,
        front_angle=62.5,
        back_angle=117.5,
        x_offset=0.5,
        z_offset=-0.5,
        x_wear=0.0,
        z_wear=0.0,
        blade_width=0.0,
    )


@pytest.fixture
def grooving_tool():
    """A grooving tool with blade width."""
    return ToolCardData(
        tool_number=3,
        tool_type="Grooving/Parting",
        insert_code="Grooving",
        orientation=2,
        description="0.125 cutoff",
        nose_radius=0.005,
        front_angle=0.0,
        back_angle=0.0,
        x_offset=0.0,
        z_offset=-0.75,
        x_wear=0.0,
        z_wear=0.0,
        blade_width=0.125,
    )


@pytest.fixture
def tmp_tbl_path():
    """Provide a temporary .tbl file path, cleaned up after test."""
    path = tempfile.mktemp(suffix=".tbl")
    yield path
    if os.path.exists(path):
        os.unlink(path)
    bak = path + ".bak"
    if os.path.exists(bak):
        os.unlink(bak)


# ---------------------------------------------------------------------------
# serialize_tool tests
# ---------------------------------------------------------------------------

class TestSerializeTool:
    def test_basic_format(self, sample_tool):
        line = serialize_tool(sample_tool)
        assert line.startswith("T1 P1 ")
        assert "X+0.000000" in line
        assert "Z-1.234567" in line
        assert "D0.032000" in line
        assert "I95.0" in line
        assert "J175.0" in line
        assert "Q1" in line

    def test_x_offset_stored_as_diameter(self, boring_tool):
        """X offset 0.5 radius should be written as 1.0 diameter."""
        line = serialize_tool(boring_tool)
        assert "X+1.000000" in line

    def test_nose_radius_stored_as_diameter(self, sample_tool):
        """nose_radius 0.016 should be written as D0.032000."""
        line = serialize_tool(sample_tool)
        assert "D0.032000" in line

    def test_metadata_encoding(self, sample_tool):
        line = serialize_tool(sample_tool)
        assert ";type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing" in line

    def test_grooving_type_encoding(self, grooving_tool):
        line = serialize_tool(grooving_tool)
        assert "type=grooving_parting" in line
        assert "blade=0.125" in line

    def test_all_type_encodings(self):
        """Every tool type should serialize to a known key."""
        types_and_keys = [
            ("Turning RH", "turning_rh"),
            ("Turning LH", "turning_lh"),
            ("Boring Bar", "boring_bar"),
            ("Threading External", "threading_external"),
            ("Threading Internal", "threading_internal"),
            ("Grooving/Parting", "grooving_parting"),
            ("Knurling", "knurling"),
            ("Custom", "custom"),
        ]
        for tool_type, expected_key in types_and_keys:
            tool = ToolCardData(
                tool_number=1, tool_type=tool_type, insert_code="CNMG",
                orientation=1, description="", nose_radius=0.016,
                front_angle=95.0, back_angle=175.0, x_offset=0.0,
                z_offset=0.0, x_wear=0.0, z_wear=0.0, blade_width=0.0,
            )
            line = serialize_tool(tool)
            assert f"type={expected_key}" in line

    def test_precision_offsets_6_decimals(self):
        """Offsets should have exactly 6 decimal places."""
        tool = ToolCardData(
            tool_number=1, tool_type="Turning RH", insert_code="CNMG",
            orientation=1, description="", nose_radius=0.0165,
            front_angle=95.0, back_angle=175.0, x_offset=0.1234567,
            z_offset=-0.9876543, x_wear=0.0, z_wear=0.0, blade_width=0.0,
        )
        line = serialize_tool(tool)
        # X = 0.1234567 * 2 = 0.2469134
        assert "X+0.246913" in line
        assert "Z-0.987654" in line

    def test_precision_angles_1_decimal(self):
        """Angles should have exactly 1 decimal place."""
        tool = ToolCardData(
            tool_number=1, tool_type="Turning RH", insert_code="CNMG",
            orientation=1, description="", nose_radius=0.016,
            front_angle=62.5, back_angle=117.5, x_offset=0.0,
            z_offset=0.0, x_wear=0.0, z_wear=0.0, blade_width=0.0,
        )
        line = serialize_tool(tool)
        assert "I62.5" in line
        assert "J117.5" in line

    def test_wear_offsets_not_stored(self, sample_tool):
        """Wear offsets should not appear in the serialized line."""
        sample_tool.x_wear = 0.005
        sample_tool.z_wear = -0.003
        line = serialize_tool(sample_tool)
        # The line should not contain wear-specific fields
        # Wear values should not affect X or Z in the output
        assert "X+0.000000" in line  # x_offset is 0.0, not affected by wear


# ---------------------------------------------------------------------------
# deserialize_tool tests
# ---------------------------------------------------------------------------

class TestDeserializeTool:
    def test_basic_parse(self):
        line = "T1 P1 X+0.000000 Z-1.234567 D0.032000 I95.0 J175.0 Q1 ;type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing"
        tool = deserialize_tool(line)
        assert tool.tool_number == 1
        assert tool.tool_type == "Turning RH"
        assert tool.insert_code == "CNMG"
        assert tool.orientation == 1
        assert tool.description == "CNMG 432 roughing"
        assert abs(tool.nose_radius - 0.016) < 1e-7
        assert abs(tool.front_angle - 95.0) < 0.1
        assert abs(tool.back_angle - 175.0) < 0.1
        assert abs(tool.z_offset - (-1.234567)) < 1e-7

    def test_x_diameter_to_radius(self):
        """X in file is diameter; should be halved to radius."""
        line = "T1 P1 X+1.000000 Z-0.500000 D0.032000 I62.5 J117.5 Q5 ;type=boring_bar|insert=DCMT|blade=0.000|desc=test"
        tool = deserialize_tool(line)
        assert abs(tool.x_offset - 0.5) < 1e-7

    def test_nose_diameter_to_radius(self):
        """D in file is diameter; should be halved to radius."""
        line = "T1 P1 X+0.000000 Z+0.000000 D0.064000 I95.0 J175.0 Q1 ;type=turning_rh|insert=CNMG|blade=0.000|desc="
        tool = deserialize_tool(line)
        assert abs(tool.nose_radius - 0.032) < 1e-7

    def test_missing_metadata_defaults(self):
        """Lines without metadata comment should use defaults."""
        line = "T3 P3 X+0.000000 Z-0.500000 D0.032000 I95.0 J175.0 Q1"
        tool = deserialize_tool(line)
        assert tool.tool_type == "Turning RH"
        assert tool.insert_code == "CNMG"
        assert tool.blade_width == 0.0
        assert tool.description == ""

    def test_wear_defaults_to_zero(self):
        """Wear offsets should always be 0.0 on load."""
        line = "T1 P1 X+0.000000 Z-1.000000 D0.032000 I95.0 J175.0 Q1 ;type=turning_rh|insert=CNMG|blade=0.000|desc=test"
        tool = deserialize_tool(line)
        assert tool.x_wear == 0.0
        assert tool.z_wear == 0.0

    def test_malformed_line_raises(self):
        """Malformed lines should raise ValueError."""
        with pytest.raises(ValueError):
            deserialize_tool("this is not a valid line")

    def test_empty_line_raises(self):
        with pytest.raises(ValueError):
            deserialize_tool("")

    def test_partial_metadata(self):
        """Lines with partial metadata should fill missing keys with defaults."""
        line = "T1 P1 X+0.000000 Z-1.000000 D0.032000 I95.0 J175.0 Q1 ;type=boring_bar|insert=CCMT"
        tool = deserialize_tool(line)
        assert tool.tool_type == "Boring Bar"
        assert tool.insert_code == "CCMT"
        assert tool.blade_width == 0.0
        assert tool.description == ""


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_serialize_deserialize_roundtrip(self, sample_tool):
        """Serialize then deserialize should produce equivalent data."""
        line = serialize_tool(sample_tool)
        parsed = deserialize_tool(line)
        assert parsed.tool_number == sample_tool.tool_number
        assert parsed.tool_type == sample_tool.tool_type
        assert parsed.insert_code == sample_tool.insert_code
        assert parsed.orientation == sample_tool.orientation
        assert parsed.description == sample_tool.description
        assert abs(parsed.nose_radius - sample_tool.nose_radius) < 1e-6
        assert abs(parsed.front_angle - sample_tool.front_angle) < 0.1
        assert abs(parsed.back_angle - sample_tool.back_angle) < 0.1
        assert abs(parsed.x_offset - sample_tool.x_offset) < 1e-6
        assert abs(parsed.z_offset - sample_tool.z_offset) < 1e-6
        assert abs(parsed.blade_width - sample_tool.blade_width) < 1e-3

    def test_roundtrip_with_nonzero_x(self, boring_tool):
        line = serialize_tool(boring_tool)
        parsed = deserialize_tool(line)
        assert abs(parsed.x_offset - boring_tool.x_offset) < 1e-6

    def test_roundtrip_grooving(self, grooving_tool):
        line = serialize_tool(grooving_tool)
        parsed = deserialize_tool(line)
        assert abs(parsed.blade_width - 0.125) < 1e-3
        assert parsed.tool_type == "Grooving/Parting"


# ---------------------------------------------------------------------------
# File I/O tests
# ---------------------------------------------------------------------------

class TestFileIO:
    def test_save_and_load(self, sample_tool, boring_tool, tmp_tbl_path):
        tools = [sample_tool, boring_tool]
        save_tool_table(tools, tmp_tbl_path)
        loaded = load_tool_table(tmp_tbl_path)
        assert len(loaded) == 2
        assert loaded[0].tool_number == 1
        assert loaded[1].tool_number == 2

    def test_load_skips_blank_lines(self, sample_tool, tmp_tbl_path):
        """Blank lines in the file should be skipped."""
        line = serialize_tool(sample_tool)
        with open(tmp_tbl_path, "w") as f:
            f.write(f"\n\n{line}\n\n")
        loaded = load_tool_table(tmp_tbl_path)
        assert len(loaded) == 1

    def test_load_skips_malformed_lines(self, sample_tool, tmp_tbl_path):
        """Malformed lines should be skipped without raising."""
        line = serialize_tool(sample_tool)
        with open(tmp_tbl_path, "w") as f:
            f.write(f"this is garbage\n{line}\nalso garbage\n")
        loaded = load_tool_table(tmp_tbl_path)
        assert len(loaded) == 1
        assert loaded[0].tool_number == 1

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_tool_table("/nonexistent/path/tool.tbl")

    def test_save_creates_directory(self, sample_tool):
        """save_tool_table should create parent directories if needed."""
        tmp_dir = tempfile.mkdtemp()
        nested_path = os.path.join(tmp_dir, "sub", "dir", "tool.tbl")
        save_tool_table([sample_tool], nested_path)
        assert os.path.exists(nested_path)
        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir)


# ---------------------------------------------------------------------------
# Backup tests
# ---------------------------------------------------------------------------

class TestBackup:
    def test_create_backup(self, sample_tool, tmp_tbl_path):
        save_tool_table([sample_tool], tmp_tbl_path)
        bak_path = create_backup(tmp_tbl_path)
        assert bak_path == tmp_tbl_path + ".bak"
        assert os.path.exists(bak_path)
        # Backup content should match original
        with open(tmp_tbl_path) as f:
            original = f.read()
        with open(bak_path) as f:
            backup = f.read()
        assert original == backup

    def test_backup_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            create_backup("/nonexistent/file.tbl")
