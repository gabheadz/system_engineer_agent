from pathlib import Path

import pytest

from system_engineer.cli import build_parser, main, resolve_folders
from system_engineer.folders import FolderListError, read_folder_list


def test_reads_one_path_per_line_and_strips_whitespace(tmp_path):
    listing = tmp_path / "folders.txt"
    listing.write_text("./svc-a\n\n  ./svc b  \n\t./svc-c\n")
    assert read_folder_list(listing) == [Path("./svc-a"), Path("./svc b"), Path("./svc-c")]


def test_expands_home(tmp_path):
    listing = tmp_path / "folders.txt"
    listing.write_text("~/components/svc-a\n")
    assert read_folder_list(listing) == [Path.home() / "components" / "svc-a"]


def test_preserves_relative_order(tmp_path):
    listing = tmp_path / "folders.txt"
    listing.write_text("svc-b\nsvc-a\n")
    assert read_folder_list(listing) == [Path("svc-b"), Path("svc-a")]


def test_missing_file_raises(tmp_path):
    missing = tmp_path / "missing.txt"
    with pytest.raises(FolderListError, match=str(missing)):
        read_folder_list(missing)


def test_blank_file_raises(tmp_path):
    listing = tmp_path / "folders.txt"
    listing.write_text("\n   \n")
    with pytest.raises(FolderListError, match="contains no folder paths"):
        read_folder_list(listing)


def test_invalid_utf8_raises(tmp_path):
    listing = tmp_path / "folders.txt"
    listing.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(FolderListError, match="Cannot read folder list"):
        read_folder_list(listing)


def test_resolve_folders_combines_cli_and_files(tmp_path):
    first = tmp_path / "first.txt"
    first.write_text("from-file-1\n")
    second = tmp_path / "second.txt"
    second.write_text("from-file-2\n")
    assert resolve_folders([Path("cli-folder")], [first, second]) == [
        Path("cli-folder"),
        Path("from-file-1"),
        Path("from-file-2"),
    ]


def test_resolve_folders_requires_at_least_one_source():
    with pytest.raises(FolderListError, match="no folders to scan"):
        resolve_folders([], None)


def test_parser_accepts_repeatable_folders_file():
    args = build_parser().parse_args(["-f", "a.txt", "--folders-file", "b.txt", "svc"])
    assert args.folders == [Path("svc")]
    assert args.folders_file == [Path("a.txt"), Path("b.txt")]


def test_main_reports_missing_folder_list(tmp_path, capsys):
    code = main(["--folders-file", str(tmp_path / "missing.txt")])
    assert code == 2
    assert "Cannot read folder list" in capsys.readouterr().err


def test_main_requires_folders_or_file(capsys):
    assert main([]) == 2
    assert "no folders to scan" in capsys.readouterr().err
