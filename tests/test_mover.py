"""
Unit tests for dropsort.mover.
"""

from dropsort.mover import safe_move


def test_basic_move(tmp_path):
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()

    file_a = src_dir / "report.pdf"
    file_a.write_text("sample content", encoding="utf-8")

    result = safe_move(file_a, dest_dir)

    # Destination folder created
    assert dest_dir.exists()
    assert result == dest_dir / "report.pdf"
    assert result.exists()
    assert result.read_text(encoding="utf-8") == "sample content"
    # Source is gone afterwards
    assert not file_a.exists()


def test_collision_handling(tmp_path):
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    # Pre-existing file in dest
    original = dest_dir / "document.docx"
    original.write_text("original content", encoding="utf-8")

    # First conflicting file
    incoming_1 = src_dir / "document.docx"
    incoming_1.write_text("first conflict", encoding="utf-8")

    res_1 = safe_move(incoming_1, dest_dir)
    assert res_1 == dest_dir / "document (1).docx"
    assert res_1.exists()
    assert res_1.read_text(encoding="utf-8") == "first conflict"
    assert original.read_text(encoding="utf-8") == "original content"  # Never overwritten!

    # Second conflicting file
    incoming_2 = src_dir / "document.docx"
    incoming_2.write_text("second conflict", encoding="utf-8")

    res_2 = safe_move(incoming_2, dest_dir)
    assert res_2 == dest_dir / "document (2).docx"
    assert res_2.exists()
    assert res_2.read_text(encoding="utf-8") == "second conflict"
    assert original.read_text(encoding="utf-8") == "original content"


def test_collision_with_no_extension(tmp_path):
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    (dest_dir / "README").write_text("first", encoding="utf-8")
    (src_dir / "README").write_text("second", encoding="utf-8")

    res = safe_move(src_dir / "README", dest_dir)
    assert res == dest_dir / "README (1)"
    assert res.read_text(encoding="utf-8") == "second"
    assert (dest_dir / "README").read_text(encoding="utf-8") == "first"
