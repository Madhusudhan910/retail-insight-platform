from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.automation.fabric_client import FabricClient

BASE_URL = "https://fabric.test/v1"


class FakeCredential:
    def get_token(self, *scopes: str) -> SimpleNamespace:
        return SimpleNamespace(token="fake-token")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@pytest.fixture
def client() -> FabricClient:
    return FabricClient(base_url=BASE_URL, credential=FakeCredential(), max_retries=2)
