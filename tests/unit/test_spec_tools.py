import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("# no front matter\n", "missing YAML front matter"),
        ("---\nrequirements: [\n---\n", "invalid YAML front matter"),
    ],
)
def test_validate_specs_reports_malformed_frontmatter(
    tmp_path: Path, content: str, message: str
) -> None:
    module = load_script("validate_specs")
    spec_path = tmp_path / "SPEC-bad.md"
    spec_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        module.load_frontmatter(spec_path)


@pytest.mark.parametrize(
    "content",
    [
        "# no front matter\n",
        "---\nrequirements: [\n---\n",
    ],
)
def test_traceability_rejects_malformed_frontmatter_without_omission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    module = load_script("generate_traceability")
    spec_root = tmp_path / "specs"
    spec_root.mkdir()
    (spec_root / "SPEC-bad.md").write_text(content, encoding="utf-8")
    (spec_root / "verification-map.yaml").write_text("verifications: {}\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(SystemExit, match="malformed spec front matter"):
        module.collect()
