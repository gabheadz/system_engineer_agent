from system_engineer.detect import detect_stack


def test_java_by_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    assert detect_stack(tmp_path) == "java"


def test_elixir_by_mix(tmp_path):
    (tmp_path / "mix.exs").write_text("")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "a.ex").write_text("")
    assert detect_stack(tmp_path) == "elixir"


def test_majority_wins_and_skips_deps(tmp_path):
    for i in range(3):
        (tmp_path / f"A{i}.java").write_text("")
    (tmp_path / "deps").mkdir()
    for i in range(50):
        (tmp_path / "deps" / f"x{i}.ex").write_text("")
    assert detect_stack(tmp_path) == "java"


def test_python_by_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "app.py").write_text("")
    assert detect_stack(tmp_path) == "python"


def test_unknown(tmp_path):
    (tmp_path / "readme.txt").write_text("")
    assert detect_stack(tmp_path) is None
