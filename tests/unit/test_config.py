from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.automation.config import load_config


def test_load_config_dev_succeeds():
    config = load_config("dev")
    assert config.environment == "dev"
    assert config.workspace_id


def test_load_config_missing_environment_raises():
    with pytest.raises(FileNotFoundError):
        load_config("staging")


def test_load_config_invalid_yaml_raises_validation_error(tmp_path):
    (tmp_path / "broken.yaml").write_text("environment: broken\n")
    with pytest.raises(ValidationError):
        load_config("broken", config_dir=tmp_path)
