"""Lädt config.toml und stellt Pfade bereit."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
HISTORY_FILE = DATA_DIR / "history.json"


@dataclass
class Config:
    raw: dict

    def __getitem__(self, key: str) -> dict:
        return self.raw[key]

    @property
    def general(self) -> dict:
        return self.raw["allgemein"]


def load_config(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Config(raw)
