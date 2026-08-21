from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_SCOPE = "https://api.fabric.microsoft.com/.default"


class TokenCredential(Protocol):
    def get_token(self, *scopes: str) -> Any: ...


class FabricApiError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.correlation_id = correlation_id


class FabricAuthError(FabricApiError):
    pass


class FabricNotFoundError(FabricApiError):
    pass


class FabricRateLimitError(FabricApiError):
    def __init__(self, message: str, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class FabricOperationTimeoutError(FabricApiError):
    pass


class FabricClient:
    def __init__(
        self,
        base_url: str,
        credential: TokenCredential,
        scope: str = DEFAULT_SCOPE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._scope = scope
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def _auth_header(self) -> dict[str, str]:
        token = self._credential.get_token(self._scope)
        return {"Authorization": f"Bearer {token.token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        headers = {**self._auth_header(), **kwargs.pop("headers", {})}

        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(method, url, headers=headers, **kwargs)
            except httpx.TimeoutException as exc:
                if attempt > self._max_retries:
                    raise FabricApiError(
                        f"Timed out calling {method} {path} after {attempt} attempts"
                    ) from exc
                self._backoff_sleep(attempt)
                continue

            correlation_id = response.headers.get("x-ms-request-id")

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 2**attempt))
                if attempt > self._max_retries:
                    raise FabricRateLimitError(
                        f"Rate limited on {method} {path}",
                        retry_after=retry_after,
                        status_code=429,
                        correlation_id=correlation_id,
                    )
                logger.warning(
                    "Rate limited on %s %s, retrying in %.1fs", method, path, retry_after
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                if attempt > self._max_retries:
                    raise FabricApiError(
                        f"Server error {response.status_code} on {method} {path}",
                        status_code=response.status_code,
                        correlation_id=correlation_id,
                    )
                self._backoff_sleep(attempt)
                continue

            if response.status_code in (401, 403):
                raise FabricAuthError(
                    f"Auth failed ({response.status_code}) on {method} {path}",
                    status_code=response.status_code,
                    correlation_id=correlation_id,
                )

            if response.status_code == 404:
                raise FabricNotFoundError(
                    f"Not found on {method} {path}",
                    status_code=response.status_code,
                    correlation_id=correlation_id,
                )

            if response.status_code >= 400:
                raise FabricApiError(
                    f"Request failed ({response.status_code}) on {method} {path}: {response.text}",
                    status_code=response.status_code,
                    correlation_id=correlation_id,
                )

            return response

    def _backoff_sleep(self, attempt: int) -> None:
        time.sleep(min(2**attempt, 30))

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/workspaces/{workspace_id}")
        return response.json()

    def create_item(self, workspace_id: str, item: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"/workspaces/{workspace_id}/items", json=item)
        return response.json()

    def update_item(
        self, workspace_id: str, item_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._request(
            "PATCH", f"/workspaces/{workspace_id}/items/{item_id}", json=payload
        )
        return response.json()

    def delete_item(self, workspace_id: str, item_id: str) -> None:
        self._request("DELETE", f"/workspaces/{workspace_id}/items/{item_id}")

    def wait_for_operation(
        self,
        operation_url: str,
        timeout_seconds: float = 600,
        poll_interval_seconds: float = 5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds

        while True:
            response = self._request("GET", operation_url)
            body = response.json()
            status = body.get("status")

            if status == "Succeeded":
                return body
            if status == "Failed":
                raise FabricApiError(f"Operation failed: {body.get('error')}")
            if status is None:
                raise FabricApiError(f"Malformed operation response: {body}")

            if time.monotonic() >= deadline:
                raise FabricOperationTimeoutError(
                    f"Operation {operation_url} did not complete within {timeout_seconds}s"
                )

            time.sleep(poll_interval_seconds)
