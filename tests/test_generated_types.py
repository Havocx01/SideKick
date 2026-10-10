"""The public frontend contract must be reproducible from backend models."""
from pathlib import Path

from scripts.generate_types import render


def test_public_library_contract_is_generated():
    generated = render()
    for name in ("LibraryFolderInput", "LibraryFolder", "LibraryItemRef", "LibraryItem", "LibrarySnapshot", "LibraryUpdate"):
        assert f"export interface {name} {{" in generated
    assert 'action: "rename" | "move" | "archive" | "restore";' in generated


def test_checked_in_types_match_generation():
    path = Path(__file__).resolve().parents[1] / "frontend/src/api/types.ts"
    assert path.read_bytes() == render().encode("utf-8")
