"""The public frontend contract must be reproducible from backend models."""
from pathlib import Path

from scripts.generate_types import emit_definition, render, ts_type


def test_literal_types_preserve_json_value_types():
    assert ts_type({'const': 1}, {}) == '1'
    assert ts_type({'const': True}, {}) == 'true'
    assert ts_type({'enum': [1, 2]}, {}) == '1 | 2'
    assert ts_type({'enum': ['pooled', 'per_equipment']}, {}) == '"pooled" | "per_equipment"'
    assert emit_definition('Version', {'enum': [1, 2]}, {}) == 'export type Version = 1 | 2;\n'


def test_public_library_contract_is_generated():
    generated = render()
    for name in ("LibraryFolderInput", "LibraryFolder", "LibraryItemRef", "LibraryItem", "LibrarySnapshot", "LibraryUpdate"):
        assert f"export interface {name} {{" in generated
    assert 'action: "rename" | "move" | "archive" | "restore";' in generated


def test_checked_in_types_match_generation():
    path = Path(__file__).resolve().parents[1] / "frontend/src/api/types.ts"
    assert path.read_bytes() == render().encode("utf-8")
