from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

class EnvironmentConfig(BaseModel):
    environment: str
    workspace_id: str
    api_base_url: str
    api_scope: str = Field(default="https://api.fabric.microsoft.com/.default")


def load_config(environment: str, config_dir: Path = CONFIG_DIR) -> EnvironmentConfig:
    path = config_dir / f"{environment}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No config file for environment '{environment}' at {path}")

    raw = yaml.safe_load(path.read_text())
    if not raw:
        raise ValueError(f"Config file {path} is empty or invalid")

    return EnvironmentConfig(**raw)