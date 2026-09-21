"""Test package for shared fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _isolate_user_config() -> None:
    """Keep every test run out of the real application config.

    A test that saves settings must never rewrite the user's own
    ``config.json``; that is how a temporary output root once leaked into a
    real run.
    """
    if os.environ.get("NOVEL_PIPELINE_CONFIG_DIR"):
        return
    directory = Path(tempfile.gettempdir()) / "novel-pipeline-v2-tests"
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["NOVEL_PIPELINE_CONFIG_DIR"] = str(directory)


_isolate_user_config()

