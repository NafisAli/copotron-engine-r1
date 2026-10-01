import json
import sys
import subprocess
import pytest
from pathlib import Path
from copotron.cli import main
from copotron.core.vault import get_vault_path

def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "copotron" in captured.out
    assert "domains" in captured.out
    assert "search" in captured.out
    assert "navigate" in captured.out
    assert "crystallize" in captured.out
    assert "validate" in captured.out
    assert "index" in captured.out
    assert "setup" in captured.out

def test_cli_subcommand_helps(capsys):
    subcommands = ["domains", "search", "navigate", "crystallize", "validate", "index", "setup"]
    for subcmd in subcommands:
        with pytest.raises(SystemExit) as exc_info:
            main([subcmd, "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert subcmd in captured.out.lower()

def test_cli_domains(capsys):
    ret = main(["domains", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    # The active vault has domains
    if data:
        assert "id" in data[0]
        assert "title" in data[0]

def test_cli_search(capsys):
    ret = main(["search", "Root", "--limit", "3", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) <= 3
    if data:
        assert "id" in data[0]
        assert "title" in data[0]

def test_cli_navigate(capsys):
    ret = main(["navigate", "00000000", "--direction", "down", "--limit", "5", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    if data:
        assert "id" in data[0]
        assert "title" in data[0]

def test_cli_validate(capsys):
    ret = main(["validate", "--json"])
    assert ret in (0, 1)  # 0 if clean, 1 if issues found
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "valid" in data

def test_cli_index(capsys):
    ret = main(["index", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "indexed" in data

def test_cli_crystallize_dry_run_or_create(tmp_path, monkeypatch, capsys):
    # Test crystallize single node in tmp vault
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    root_md = vault_dir / "00000000-root.md"
    root_md.write_text(
        "---\nid: \"00000000\"\ntitle: Root Hub\ndate: \"2026-09-01\"\nsummary: Root hub\ntype: declarative\nstatus: active\n---\n# Root\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))

    ret = main([
        "crystallize",
        "--title", "CLI Created Node",
        "--summary", "Created via CLI unit test",
        "--type", "episodic",
        "--parents", "00000000",
        "--json"
    ])
    assert ret == 0
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["title"] == "CLI Created Node"
    new_id = res["id"]
    matches = list(vault_dir.glob(f"{new_id}*.md"))
    assert len(matches) == 1

def test_installed_console_script():
    """Verify that 'copotron --help' works via the entry point."""
    result = subprocess.run(
        ["uv", "run", "copotron", "--help"],
        capture_output=True,
        text=True,
        check=False
    )
    assert result.returncode == 0
    assert "copotron" in result.stdout
    assert "crystallize" in result.stdout
