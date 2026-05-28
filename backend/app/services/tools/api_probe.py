from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ValidationAppError


def run_api_test(arguments: dict[str, Any]) -> dict[str, Any]:
    method = str(arguments.get("method") or "GET").upper()
    path = str(arguments.get("path") or "/api/v1/health")
    headers = arguments.get("headers") if isinstance(arguments.get("headers"), dict) else {}
    body = arguments.get("body")
    expected_status = int(arguments.get("expected_status") or arguments.get("expectedStatus") or 200)
    started = time.perf_counter()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValidationAppError(f"unsupported HTTP method: {method}")
    response = _request(method, path, headers=headers, body=body)
    duration_ms = int((time.perf_counter() - started) * 1000)
    assertion_passed = response["status_code"] == expected_status
    return {
        "status": "succeeded" if assertion_passed else "failed",
        "capability_level": "real",
        "method": method,
        "path": path,
        "status_code": response["status_code"],
        "expected_status": expected_status,
        "assertion_passed": assertion_passed,
        "duration_ms": duration_ms,
        "response_summary": response["summary"],
        "headers": response["headers"],
    }


def _request(method: str, path: str, *, headers: dict[str, Any], body: Any) -> dict[str, Any]:
    if _is_absolute_url(path):
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.request(method, path, headers=_string_headers(headers), json=body)
        return _response_payload(response.status_code, response.headers, response.text)
    if not path.startswith("/"):
        path = f"/{path}"
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.request(method, path, headers=_string_headers(headers), json=body)
    return _response_payload(response.status_code, response.headers, response.text)


def _response_payload(status_code: int, headers: Any, text: str) -> dict[str, Any]:
    summary: Any = text[:4_000]
    try:
        summary = json.loads(text)
    except Exception:
        pass
    return {
        "status_code": status_code,
        "headers": {key.lower(): value for key, value in dict(headers).items()},
        "summary": summary,
    }


def _is_absolute_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _string_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}
