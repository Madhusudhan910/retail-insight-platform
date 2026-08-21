from __future__ import annotations

import httpx
import pytest
import respx

from src.automation.fabric_client import (
    FabricApiError,
    FabricAuthError,
    FabricNotFoundError,
    FabricOperationTimeoutError,
    FabricRateLimitError,
)
from tests.unit.conftest import BASE_URL


@respx.mock
def test_get_workspace_success(client):
    route = respx.get(f"{BASE_URL}/workspaces/ws-1").mock(
        return_value=httpx.Response(200, json={"id": "ws-1", "name": "Dev"})
    )
    result = client.get_workspace("ws-1")
    assert result == {"id": "ws-1", "name": "Dev"}
    assert route.called


@respx.mock
def test_get_workspace_401_raises_auth_error(client):
    respx.get(f"{BASE_URL}/workspaces/ws-1").mock(return_value=httpx.Response(401))
    with pytest.raises(FabricAuthError):
        client.get_workspace("ws-1")


@respx.mock
def test_get_workspace_403_raises_auth_error(client):
    respx.get(f"{BASE_URL}/workspaces/ws-1").mock(return_value=httpx.Response(403))
    with pytest.raises(FabricAuthError):
        client.get_workspace("ws-1")


@respx.mock
def test_get_workspace_404_raises_not_found(client):
    respx.get(f"{BASE_URL}/workspaces/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(FabricNotFoundError):
        client.get_workspace("missing")


@respx.mock
def test_get_workspace_429_then_success_retries(client):
    route = respx.get(f"{BASE_URL}/workspaces/ws-1")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"id": "ws-1"}),
    ]
    result = client.get_workspace("ws-1")
    assert result == {"id": "ws-1"}
    assert route.call_count == 2


@respx.mock
def test_get_workspace_429_exhausts_retries(client):
    respx.get(f"{BASE_URL}/workspaces/ws-1").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )
    with pytest.raises(FabricRateLimitError):
        client.get_workspace("ws-1")


@respx.mock
def test_get_workspace_500_then_success_retries(client):
    route = respx.get(f"{BASE_URL}/workspaces/ws-1")
    route.side_effect = [httpx.Response(500), httpx.Response(200, json={"id": "ws-1"})]
    result = client.get_workspace("ws-1")
    assert result == {"id": "ws-1"}


@respx.mock
def test_get_workspace_500_exhausts_retries(client):
    respx.get(f"{BASE_URL}/workspaces/ws-1").mock(return_value=httpx.Response(500))
    with pytest.raises(FabricApiError):
        client.get_workspace("ws-1")


@respx.mock
def test_get_workspace_timeout_then_success_retries(client):
    route = respx.get(f"{BASE_URL}/workspaces/ws-1")
    route.side_effect = [
        httpx.TimeoutException("timed out"),
        httpx.Response(200, json={"id": "ws-1"}),
    ]
    result = client.get_workspace("ws-1")
    assert result == {"id": "ws-1"}


@respx.mock
def test_get_workspace_timeout_exhausts_retries(client):
    respx.get(f"{BASE_URL}/workspaces/ws-1").mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(FabricApiError):
        client.get_workspace("ws-1")


@respx.mock
def test_create_item_success(client):
    respx.post(f"{BASE_URL}/workspaces/ws-1/items").mock(
        return_value=httpx.Response(201, json={"id": "item-1"})
    )
    result = client.create_item("ws-1", {"displayName": "Sales"})
    assert result == {"id": "item-1"}


@respx.mock
def test_delete_item_success(client):
    respx.delete(f"{BASE_URL}/workspaces/ws-1/items/item-1").mock(return_value=httpx.Response(200))
    client.delete_item("ws-1", "item-1")


@respx.mock
def test_wait_for_operation_success(client):
    op_url = f"{BASE_URL}/operations/op-1"
    route = respx.get(op_url)
    route.side_effect = [
        httpx.Response(200, json={"status": "Running"}),
        httpx.Response(200, json={"status": "Succeeded", "result": {"id": "item-1"}}),
    ]
    result = client.wait_for_operation(op_url, timeout_seconds=10, poll_interval_seconds=0)
    assert result["status"] == "Succeeded"


@respx.mock
def test_wait_for_operation_failed_status_raises(client):
    op_url = f"{BASE_URL}/operations/op-1"
    respx.get(op_url).mock(
        return_value=httpx.Response(200, json={"status": "Failed", "error": "boom"})
    )
    with pytest.raises(FabricApiError):
        client.wait_for_operation(op_url)


@respx.mock
def test_wait_for_operation_malformed_response_raises(client):
    op_url = f"{BASE_URL}/operations/op-1"
    respx.get(op_url).mock(return_value=httpx.Response(200, json={"weird": "shape"}))
    with pytest.raises(FabricApiError):
        client.wait_for_operation(op_url)


@respx.mock
def test_wait_for_operation_timeout_raises(client):
    op_url = f"{BASE_URL}/operations/op-1"
    respx.get(op_url).mock(return_value=httpx.Response(200, json={"status": "Running"}))
    with pytest.raises(FabricOperationTimeoutError):
        client.wait_for_operation(op_url, timeout_seconds=0, poll_interval_seconds=0)
