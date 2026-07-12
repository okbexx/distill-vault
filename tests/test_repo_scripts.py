import os
from pathlib import Path


def test_run_tests_wrapper_exists_and_is_executable():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_tests.sh"

    assert script.exists()
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert os.access(script, os.X_OK)
