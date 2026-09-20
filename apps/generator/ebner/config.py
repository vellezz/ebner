"""Configuration loading.

Everything the randomiser and the model routing need lives in YAML under
config/, so changing the rhythm of the diary or swapping a model is an edit to
data rather than to code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .d1 import REPO

CONFIG_DIR = REPO / "apps" / "generator" / "config"
PROMPTS_DIR = REPO / "prompts"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing config: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def rhythm() -> dict:
    return load("rhythm.yaml")


def prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing prompt: {path}")
    return path.read_text(encoding="utf-8")
