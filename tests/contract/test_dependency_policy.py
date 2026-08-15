import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_repository_dependency_policy_is_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_dependency_policy.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
